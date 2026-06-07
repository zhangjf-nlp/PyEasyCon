import threading
import time
from typing import Optional, List

import serial
import serial.tools.list_ports

from .protocol import GamePadKey, Direction, SwitchButton, SwitchHAT, SwitchStick, SwitchReport
from .serial_transport import EzDvCommand, Reply


def sleep(seconds: float, end: Optional[float] = None) -> None:
    start = time.time()
    if end is None:
        mid = start + seconds - 0.1
        end = start + seconds
    else:
        mid = end - 0.1
    while True:
        if time.time() >= mid:
            if time.time() >= end:
                return
        else:
            time.sleep(0.05)


class EasyConController:
    MINIMAL_INTERVAL = 30

    _KEY_TO_BUTTON = {
        GamePadKey.Y: SwitchButton.Y,
        GamePadKey.B: SwitchButton.B,
        GamePadKey.A: SwitchButton.A,
        GamePadKey.X: SwitchButton.X,
        GamePadKey.L: SwitchButton.L,
        GamePadKey.R: SwitchButton.R,
        GamePadKey.ZL: SwitchButton.ZL,
        GamePadKey.ZR: SwitchButton.ZR,
        GamePadKey.MINUS: SwitchButton.MINUS,
        GamePadKey.PLUS: SwitchButton.PLUS,
        GamePadKey.LCLICK: SwitchButton.LCLICK,
        GamePadKey.RCLICK: SwitchButton.RCLICK,
        GamePadKey.HOME: SwitchButton.HOME,
        GamePadKey.CAPTURE: SwitchButton.CAPTURE,
    }

    _KEY_TO_HAT = {
        GamePadKey.TOP: SwitchHAT.TOP,
        GamePadKey.TOP_RIGHT: SwitchHAT.TOP_RIGHT,
        GamePadKey.RIGHT: SwitchHAT.RIGHT,
        GamePadKey.DOWN_RIGHT: SwitchHAT.BOTTOM_RIGHT,
        GamePadKey.DOWN: SwitchHAT.BOTTOM,
        GamePadKey.DOWN_LEFT: SwitchHAT.BOTTOM_LEFT,
        GamePadKey.LEFT: SwitchHAT.LEFT,
        GamePadKey.TOP_LEFT: SwitchHAT.TOP_LEFT,
    }

    def __init__(self):
        self._serial: Optional[serial.Serial] = None
        self._port_name: Optional[str] = None
        self._baudrate = 115200
        self._baudrate_fallbacks = [9600, 57600, 38400, 19200]  # 覆盖多种固件波特率
        self._connected = False
        self._lock = threading.Lock()
        self._debug = False
        self._report = SwitchReport()
        self._report_dirty = False
        self._io_cond = threading.Condition()
        self._io_thread: Optional[threading.Thread] = None
        self._io_running = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    def set_debug(self, enabled: bool):
        self._debug = enabled

    def list_ports(self) -> List[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port: Optional[str] = None, timeout: float = 2.0) -> bool:
        if port is None:
            for p in self.list_ports():
                if self._try_connect_port(p, self._baudrate, timeout):
                    return True
            # 空端口参数时也尝试回退波特率
            for baud in self._baudrate_fallbacks:
                for p in self.list_ports():
                    if self._try_connect_port(p, baud, timeout):
                        return True
            return False
        # 指定端口：先尝试主波特率，再回退
        if self._try_connect_port(port, self._baudrate, timeout):
            return True
        for baud in self._baudrate_fallbacks:
            if self._try_connect_port(port, baud, timeout):
                return True
        return False

    def _try_connect_port(self, port: str, baudrate: int, timeout: float) -> bool:
        try:
            if self._debug:
                print(f"Trying {port}@{baudrate}...")

            # 关键修复：先创建 Serial 对象（不打开），设置 DTR/RTS 为低电平，
            # 再手动打开串口。避免 pyserial 默认 DTR=True 触发 CH340/Arduino
            # 兼容板的自动复位（auto-reset），导致握手失败。
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = baudrate
            ser.timeout = 0.1
            ser._dtr_state = False
            ser._rts_state = False
            ser.open()

            ser.reset_input_buffer()

            hello_bytes = bytes([EzDvCommand.Ready, EzDvCommand.Ready, EzDvCommand.Hello])
            dead_air_wait = 0.15  # 首轮快速等待，适配无自动复位的 MCU

            for attempt in range(2):
                ser.reset_input_buffer()
                ser.write(hello_bytes)

                if self._debug:
                    print(f"[{port}] >> {' '.join(f'{b:02X}' for b in hello_bytes)}")

                deadline = time.time() + (timeout if attempt > 0 else dead_air_wait)
                response = b''
                while time.time() < deadline:
                    if ser.in_waiting:
                        response += ser.read(ser.in_waiting)
                        break
                    time.sleep(0.05)

                if self._debug:
                    print(f"[{port}] << {' '.join(f'{b:02X}' for b in response) if response else '(无数据)'}")

                if len(response) >= 1 and response[0] == Reply.Hello:
                    if self._debug:
                        print(f"Connected to {port}@{baudrate}")
                    self._serial = ser
                    self._port_name = port
                    self._baudrate = baudrate
                    self._connected = True
                    self._start_io_thread()
                    return True

                # 首轮未响应：可能是自动复位还在启动，等够再试一次
                if attempt == 0 and not response:
                    time.sleep(max(0, timeout - dead_air_wait - 0.1))

            if self._debug:
                print(f"No valid handshake on {port}@{baudrate}")
            ser.close()
            return False

        except Exception as e:
            if self._debug:
                print(f"Failed to connect {port}: {e}")
            return False

    def disconnect(self):
        self._connected = False
        self._io_running = False
        with self._io_cond:
            self._io_cond.notify()
        if self._io_thread and self._io_thread.is_alive():
            self._io_thread.join(timeout=2.0)
        if self._serial:
            self._serial.close()
            self._serial = None

    def _start_io_thread(self):
        if self._io_thread and self._io_thread.is_alive():
            return
        self._io_running = True
        self._io_thread = threading.Thread(target=self._io_loop, daemon=True)
        self._io_thread.start()

    def _io_loop(self):
        last_send = 0.0
        while self._io_running:
            with self._io_cond:
                while self._io_running and not self._report_dirty:
                    self._io_cond.wait(timeout=0.1)
                if not self._io_running:
                    return

                now = time.time() * 1000
                dt = now - last_send
                if dt < self.MINIMAL_INTERVAL:
                    self._io_cond.wait(timeout=(self.MINIMAL_INTERVAL - dt) / 1000.0)
                    if not self._io_running:
                        return
                    continue

                report_bytes = self._report.get_bytes()
                self._report_dirty = False

            if self.is_connected:
                with self._lock:
                    try:
                        if self._debug:
                            print(f"[{self._port_name}] >> {' '.join(f'{b:02X}' for b in report_bytes)} | {self._report_to_str()}")
                        self._serial.write(report_bytes)
                        last_send = time.time() * 1000
                    except Exception:
                        self._connected = False

    def _send_report(self):
        if not self._connected:
            return
        with self._io_cond:
            self._report_dirty = True
            self._io_cond.notify()

    def _report_to_str(self) -> str:
        buttons = []
        for key, btn in self._KEY_TO_BUTTON.items():
            if self._report.button & btn:
                buttons.append(key.name)
        if self._report.hat != SwitchHAT.CENTER:
            buttons.append(f"HAT.{SwitchHAT(self._report.hat).name}")
        return f"Btn:{buttons} LX:{self._report.lx} LY:{self._report.ly} RX:{self._report.rx} RY:{self._report.ry}"

    def press(self, key: GamePadKey):
        if key in self._KEY_TO_BUTTON:
            self._report.button |= self._KEY_TO_BUTTON[key]
        elif key in self._KEY_TO_HAT:
            self._report.hat = self._KEY_TO_HAT[key]
        elif key == GamePadKey.LS:
            pass
        elif key == GamePadKey.RS:
            pass
        self._send_report()

    def release(self, key: GamePadKey):
        if key in self._KEY_TO_BUTTON:
            self._report.button &= ~self._KEY_TO_BUTTON[key]
        elif key in self._KEY_TO_HAT:
            self._report.hat = SwitchHAT.CENTER
        elif key == GamePadKey.LS:
            self._report.lx = SwitchStick.STICK_CENTER
            self._report.ly = SwitchStick.STICK_CENTER
        elif key == GamePadKey.RS:
            self._report.rx = SwitchStick.STICK_CENTER
            self._report.ry = SwitchStick.STICK_CENTER
        self._send_report()

    def release_all(self):
        self._report.reset()
        self._send_report()

    def click(self, key: GamePadKey, duration_ms: int = 50):
        self.press(key)
        sleep(duration_ms / 1000)
        self.release(key)

    def set_stick(self, stick: GamePadKey, x: int, y: int):
        if stick not in (GamePadKey.LS, GamePadKey.RS):
            raise ValueError("stick must be LS or RS")

        x = max(0, min(255, x))
        y = max(0, min(255, y))

        if stick == GamePadKey.LS:
            self._report.lx = x
            self._report.ly = y
        else:
            self._report.rx = x
            self._report.ry = y
        self._send_report()

    def click_stick(self, stick: GamePadKey, x: int, y: int, duration_ms: int = 50):
        self.set_stick(stick, x, y)
        sleep(duration_ms / 1000)
        self.set_stick(stick, SwitchStick.STICK_CENTER, SwitchStick.STICK_CENTER)

    def push_direction(self, direction: Direction, duration_ms: int = 50):
        self.click(GamePadKey(direction), duration_ms)

    def reset(self):
        self.release_all()

    def a(self, duration_ms: int = 50): self.click(GamePadKey.A, duration_ms)
    def b(self, duration_ms: int = 50): self.click(GamePadKey.B, duration_ms)
    def x(self, duration_ms: int = 50): self.click(GamePadKey.X, duration_ms)
    def y(self, duration_ms: int = 50): self.click(GamePadKey.Y, duration_ms)

    def l(self, duration_ms: int = 50): self.click(GamePadKey.L, duration_ms)
    def r(self, duration_ms: int = 50): self.click(GamePadKey.R, duration_ms)
    def zl(self, duration_ms: int = 50): self.click(GamePadKey.ZL, duration_ms)
    def zr(self, duration_ms: int = 50): self.click(GamePadKey.ZR, duration_ms)

    def minus(self, duration_ms: int = 50): self.click(GamePadKey.MINUS, duration_ms)
    def plus(self, duration_ms: int = 50): self.click(GamePadKey.PLUS, duration_ms)
    def home(self, duration_ms: int = 50): self.click(GamePadKey.HOME, duration_ms)
    def capture(self, duration_ms: int = 50): self.click(GamePadKey.CAPTURE, duration_ms)

    def up(self, duration_ms: int = 50): self.click(GamePadKey.TOP, duration_ms)
    def down(self, duration_ms: int = 50): self.click(GamePadKey.DOWN, duration_ms)
    def left(self, duration_ms: int = 50): self.click(GamePadKey.LEFT, duration_ms)
    def right(self, duration_ms: int = 50): self.click(GamePadKey.RIGHT, duration_ms)

    def lstick(self, x: int, y: int, duration_ms: int = 50):
        self.click_stick(GamePadKey.LS, x, y, duration_ms)

    def rstick(self, x: int, y: int, duration_ms: int = 50):
        self.click_stick(GamePadKey.RS, x, y, duration_ms)

    # ============== 高级控制器命令 ==============

    def _recv_byte(self, timeout: float = 0.2) -> Optional[int]:
        """等待并读取单字节响应"""
        if not self._serial:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._serial.in_waiting:
                return self._serial.read(1)[0]
            time.sleep(0.01)
        return None

    def _send_command(self, *cmd_bytes: int, timeout: float = 0.2) -> Optional[int]:
        """发送 EzDv 命令并等待单字节响应"""
        if not self._connected or not self._serial:
            return None
        with self._lock:
            try:
                self._serial.reset_input_buffer()
                self._serial.write(bytes(cmd_bytes))
                return self._recv_byte(timeout)
            except Exception:
                return None

    def change_controller_mode(self, mode: int) -> bool:
        """切换控制器模式: 1=JoyCon-L, 2=JoyCon-R, 3=Pro"""
        reply = self._send_command(
            EzDvCommand.Ready, mode, EzDvCommand.ChangeControllerMode
        )
        return reply == Reply.Ack

    def change_controller_color(self, body_rgb: tuple, button_rgb: tuple,
                                grip_l_rgb: tuple, grip_r_rgb: tuple) -> bool:
        """设置手柄颜色 (各 3 字节 RGB)。
        颜色数据内联在命令中一并发送，与 C# 版 SendSync 行为一致。"""
        if not self._connected or not self._serial:
            return False
        cmd = bytes([
            EzDvCommand.Ready, 0, 0, 12, 0,
            EzDvCommand.ChangeControllerColor,
            *body_rgb, *button_rgb, *grip_l_rgb, *grip_r_rgb,
        ])
        with self._lock:
            try:
                self._serial.reset_input_buffer()
                self._serial.write(cmd)
                reply = self._recv_byte(timeout=1.0)
                return reply == Reply.Ack
            except Exception:
                return False

    def unpair(self) -> bool:
        """取消配对（断开与主机的蓝牙连接）"""
        reply = self._send_command(EzDvCommand.Ready, EzDvCommand.UnPair)
        return reply == Reply.Ack

    def trigger_led(self) -> bool:
        """触发 LED 闪烁"""
        reply = self._send_command(EzDvCommand.Ready, EzDvCommand.LED)
        return reply == 0

    def get_version(self) -> int:
        """获取固件版本号"""
        reply = self._send_command(EzDvCommand.Ready, EzDvCommand.Version, timeout=0.5)
        if reply is not None and 0x40 <= reply <= 0x80:
            return reply
        return -1

    def flash(self, data: bytes) -> bool:
        """烧录固件（分片发送）"""
        if not self._connected or not self._serial:
            return False
        packet_size = 20
        with self._lock:
            for i in range(0, len(data), packet_size):
                chunk = data[i:i + packet_size]
                chunk_len = len(chunk)
                while True:
                    header = bytes([
                        EzDvCommand.Ready,
                        i & 0x7F, (i >> 7) & 0x7F,
                        chunk_len & 0x7F, (chunk_len >> 7) & 0x7F,
                        EzDvCommand.Flash,
                    ])
                    self._serial.reset_input_buffer()
                    self._serial.write(header)
                    reply = self._recv_byte(timeout=1.0)
                    if reply != Reply.FlashStart:
                        if not self._handshake():
                            return False
                        continue
                    self._serial.reset_input_buffer()
                    self._serial.write(chunk)
                    reply = self._recv_byte(timeout=1.0)
                    if reply == Reply.FlashEnd:
                        break
                    if not self._handshake():
                        return False
        return True

    def _handshake(self) -> bool:
        """发送握手包恢复通信"""
        if not self._serial:
            return False
        try:
            for _ in range(3):
                self._serial.write(
                    bytes([EzDvCommand.Ready, EzDvCommand.Hello])
                )
            reply = self._recv_byte(timeout=0.2)
            return reply == Reply.Hello
        except Exception:
            return False

    def remote_start(self) -> bool:
        """远程启动板载脚本"""
        reply = self._send_command(EzDvCommand.Ready, EzDvCommand.ScriptStart)
        return reply == Reply.ScriptAck

    def remote_stop(self) -> bool:
        """远程停止板载脚本"""
        reply = self._send_command(EzDvCommand.Ready, EzDvCommand.ScriptStop)
        return reply == Reply.ScriptAck

    def save_amiibo(self, index: int, amiibo_data: bytes) -> bool:
        """保存 Amiibo 数据到指定索引"""
        if not self._connected or not self._serial:
            return False
        packet_size = 20
        with self._lock:
            for i in range(0, len(amiibo_data), packet_size):
                chunk = amiibo_data[i:i + packet_size]
                chunk_len = len(chunk)
                while True:
                    header = bytes([
                        EzDvCommand.Ready,
                        i & 0x7F, (i >> 7) & 0x7F,
                        chunk_len & 0x7F, (chunk_len >> 7) & 0x7F,
                        index,
                        EzDvCommand.SaveAmiibo,
                    ])
                    self._serial.reset_input_buffer()
                    self._serial.write(header)
                    reply = self._recv_byte(timeout=1.0)
                    if reply != Reply.Ack:
                        if not self._handshake():
                            return False
                        continue
                    self._serial.reset_input_buffer()
                    self._serial.write(chunk)
                    reply = self._recv_byte(timeout=1.0)
                    if reply == Reply.Ack:
                        break
                    if not self._handshake():
                        return False
        return True

    def change_amiibo_index(self, index: int) -> bool:
        """切换当前使用的 Amiibo 索引"""
        reply = self._send_command(
            EzDvCommand.Ready, index, EzDvCommand.ChangeAmiiboIndex
        )
        return reply == Reply.Ack