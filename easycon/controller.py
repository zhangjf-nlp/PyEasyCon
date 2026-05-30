import threading
import time
from typing import Optional, List

import serial
import serial.tools.list_ports

from .protocol import GamePadKey, Direction, SwitchButton, SwitchHAT, SwitchStick, SwitchReport
from .serial_transport import EzDvCommand, Reply


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
                if self._try_connect_port(p, timeout):
                    return True
            return False
        return self._try_connect_port(port, timeout)

    def _try_connect_port(self, port: str, timeout: float) -> bool:
        try:
            if self._debug:
                print(f"Trying {port}...")

            ser = serial.Serial(port, self._baudrate, timeout=timeout)
            ser.dtr = False
            ser.rts = False

            ser.reset_input_buffer()
            ser.reset_output_buffer()

            hello_bytes = bytes([EzDvCommand.Ready, EzDvCommand.Ready, EzDvCommand.Hello])
            ser.write(hello_bytes)

            if self._debug:
                print(f"[{port}] >> {' '.join(f'{b:02X}' for b in hello_bytes)}")

            time.sleep(0.1)
            response = ser.read(ser.in_waiting or 1)

            if self._debug:
                print(f"[{port}] << {' '.join(f'{b:02X}' for b in response)}")

            if len(response) >= 1 and response[0] == Reply.Hello:
                self._serial = ser
                self._port_name = port
                self._connected = True
                self._start_io_thread()
                if self._debug:
                    print(f"Connected to {port}")
                return True

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
        self._delay(duration_ms)
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
        self._delay(duration_ms)
        self.set_stick(stick, SwitchStick.STICK_CENTER, SwitchStick.STICK_CENTER)

    def push_direction(self, direction: Direction, duration_ms: int = 50):
        self.click(GamePadKey(direction), duration_ms)

    def reset(self):
        self.release_all()

    def _delay(self, ms: int):
        if ms <= 0:
            return
        time.sleep(ms / 1000.0)

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

    def wait(self, ms: int):
        time.sleep(ms / 1000.0)