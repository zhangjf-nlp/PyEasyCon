"""
EasyCon Python API - 控制单片机操作 Nintendo Switch 的 Python 接口

Based on EasyCon project: https://github.com/EasyConNS/EasyCon
"""

import base64
import json
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, List, Callable, Tuple

import cv2
import numpy as np
import serial
import serial.tools.list_ports


class GamePadKey(IntEnum):
    """NS 手柄按键定义"""
    NONE = 0
    Y = 1
    B = 2
    A = 3
    X = 4
    L = 5
    R = 6
    ZL = 7
    ZR = 8
    MINUS = 9
    PLUS = 10
    LCLICK = 11
    RCLICK = 12
    HOME = 13
    CAPTURE = 14
    TOP = 16
    TOP_RIGHT = 17
    RIGHT = 18
    DOWN_RIGHT = 19
    DOWN = 20
    DOWN_LEFT = 21
    LEFT = 22
    TOP_LEFT = 23
    LS = 32  # 左摇杆
    RS = 33  # 右摇杆


class Direction(IntEnum):
    """方向键定义"""
    UP = GamePadKey.TOP
    UP_RIGHT = GamePadKey.TOP_RIGHT
    RIGHT = GamePadKey.RIGHT
    DOWN_RIGHT = GamePadKey.DOWN_RIGHT
    DOWN = GamePadKey.DOWN
    DOWN_LEFT = GamePadKey.DOWN_LEFT
    LEFT = GamePadKey.LEFT
    UP_LEFT = GamePadKey.TOP_LEFT


class EzDvCommand:
    """EasyCon 设备命令字节 - 与C# CommandCode.cs 保持一致"""
    Ready = 0xA5
    Debug = 0x80
    Hello = 0x81
    Flash = 0x82
    ScriptStart = 0x83
    ScriptStop = 0x84
    Version = 0x85
    LED = 0x86
    UnPair = 0x87
    ChangeControllerMode = 0x88
    ChangeControllerColor = 0x89
    SaveAmiibo = 0x90
    ChangeAmiiboIndex = 0x91


class Reply:
    """EasyCon 设备响应字节 - 与C# CommandCode.cs 保持一致"""
    Error = 0x0
    Busy = 0xFE
    Ack = 0xFF
    Hello = 0x80
    FlashStart = 0x81
    FlashEnd = 0x82
    ScriptAck = 0x83


class SwitchStick:
    """摇杆参数"""
    STICK_CENTER = 128
    STICK_MAX = 255
    STICK_MIN = 0


class SwitchButton(IntEnum):
    """NS 手柄按钮位掩码 - 与C# SwitchCommand.cs 保持一致"""
    Y = 0x01
    B = 0x02
    A = 0x04
    X = 0x08
    L = 0x10
    R = 0x20
    ZL = 0x40
    ZR = 0x80
    MINUS = 0x100
    PLUS = 0x200
    LCLICK = 0x400
    RCLICK = 0x800
    HOME = 0x1000
    CAPTURE = 0x2000


class SwitchHAT(IntEnum):
    """方向键HAT值 - 与C# SwitchCommand.cs 保持一致"""
    TOP = 0x00
    TOP_RIGHT = 0x01
    RIGHT = 0x02
    BOTTOM_RIGHT = 0x03
    BOTTOM = 0x04
    BOTTOM_LEFT = 0x05
    LEFT = 0x06
    TOP_LEFT = 0x07
    CENTER = 0x08


class SwitchReport:
    """
    Switch 手柄状态报告
    与C# SwitchReport.cs 保持一致的协议实现
    """
    def __init__(self):
        self.button: int = 0
        self.hat: int = SwitchHAT.CENTER
        self.lx: int = SwitchStick.STICK_CENTER
        self.ly: int = SwitchStick.STICK_CENTER
        self.rx: int = SwitchStick.STICK_CENTER
        self.ry: int = SwitchStick.STICK_CENTER

    def reset(self):
        """重置所有按键和摇杆"""
        self.button = 0
        self.hat = SwitchHAT.CENTER
        self.lx = SwitchStick.STICK_CENTER
        self.ly = SwitchStick.STICK_CENTER
        self.rx = SwitchStick.STICK_CENTER
        self.ry = SwitchStick.STICK_CENTER

    def get_bytes(self) -> bytes:
        """
        序列化为协议字节数组
        协议结构:
        - bit 7 (最高位): 0 = 数据字节, 1 = 结束标志
        - bit 6~0: 数据 (大端序)
        """
        serialized = []
        serialized.extend(self.button.to_bytes(2, 'big'))
        serialized.append(self.hat)
        serialized.append(self.lx)
        serialized.append(self.ly)
        serialized.append(self.rx)
        serialized.append(self.ry)

        packet = []
        n = 0
        bits = 0
        for b in serialized:
            n = (n << 8) | b
            bits += 8
            while bits >= 7:
                bits -= 7
                packet.append((n >> bits) & 0x7F)
                n &= (1 << bits) - 1

        if packet:
            packet[-1] |= 0x80
        return bytes(packet)

    def copy(self) -> "SwitchReport":
        """创建副本"""
        r = SwitchReport()
        r.button = self.button
        r.hat = self.hat
        r.lx = self.lx
        r.ly = self.ly
        r.rx = self.rx
        r.ry = self.ry
        return r


@dataclass
class ImgLabel:
    """图像标签，用于识图"""
    name: str
    image_path: Optional[str] = None
    image_base64: Optional[str] = None
    # 搜索范围 (相对于1920x1080分辨率)
    range_x: int = 0
    range_y: int = 0
    range_width: int = 1920
    range_height: int = 1080
    # 目标区域
    target_x: int = 0
    target_y: int = 0
    target_width: int = 100
    target_height: int = 100
    # 匹配阈值 0-100
    threshold: float = 80.0
    # 搜索方法
    search_method: int = cv2.TM_CCOEFF_NORMED

    def load_image(self, path: str):
        """从文件加载目标图片"""
        self.image_path = path
        with open(path, "rb") as f:
            self.image_base64 = base64.b64encode(f.read()).decode()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ImgBase64": self.image_base64 or "",
            "RangeX": self.range_x,
            "RangeY": self.range_y,
            "RangeWidth": self.range_width,
            "RangeHeight": self.range_height,
            "TargetX": self.target_x,
            "TargetY": self.target_y,
            "TargetWidth": self.target_width,
            "TargetHeight": self.target_height,
        }

    @staticmethod
    def from_dict(data: dict) -> "ImgLabel":
        label = ImgLabel(name=data.get("name", ""))
        label.image_base64 = data.get("ImgBase64", "")
        label.range_x = data.get("RangeX", 0)
        label.range_y = data.get("RangeY", 0)
        label.range_width = data.get("RangeWidth", 1920)
        label.range_height = data.get("RangeHeight", 1080)
        label.target_x = data.get("TargetX", 0)
        label.target_y = data.get("TargetY", 0)
        label.target_width = data.get("TargetWidth", 100)
        label.target_height = data.get("TargetHeight", 100)
        return label


class EasyConController:
    """
    EasyCon 主控制器类
    封装了与单片机的通信和按键控制功能
    """

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
        self._last_send_time = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    def set_debug(self, enabled: bool):
        """设置调试模式，打印通信数据"""
        self._debug = enabled

    def list_ports(self) -> List[str]:
        """列出可用串口"""
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port: Optional[str] = None, timeout: float = 2.0) -> bool:
        """
        连接单片机

        Args:
            port: 串口名称，如 "COM3" 或 "/dev/ttyUSB0"，为 None 则自动搜索
            timeout: 连接超时时间

        Returns:
            是否连接成功
        """
        if port is None:
            for p in self.list_ports():
                if self._try_connect_port(p, timeout):
                    return True
            return False
        return self._try_connect_port(port, timeout)

    def _try_connect_port(self, port: str, timeout: float) -> bool:
        """尝试连接指定串口"""
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
        """断开连接"""
        self._connected = False
        if self._serial:
            self._serial.close()
            self._serial = None

    def _send_report(self):
        """发送当前手柄状态报告"""
        if not self.is_connected:
            raise ConnectionError("Not connected to device")

        now = time.time() * 1000
        if now < self._last_send_time + self.MINIMAL_INTERVAL:
            time.sleep((self._last_send_time + self.MINIMAL_INTERVAL - now) / 1000.0)

        data = self._report.get_bytes()
        with self._lock:
            if self._debug:
                print(f"[{self._port_name}] >> {' '.join(f'{b:02X}' for b in data)} | {self._report_to_str()}")
            self._serial.write(data)
        self._last_send_time = time.time() * 1000

    def _report_to_str(self) -> str:
        """将报告转换为可读字符串"""
        buttons = []
        for key, btn in self._KEY_TO_BUTTON.items():
            if self._report.button & btn:
                buttons.append(key.name)
        if self._report.hat != SwitchHAT.CENTER:
            buttons.append(f"HAT.{SwitchHAT(self._report.hat).name}")
        return f"Btn:{buttons} LX:{self._report.lx} LY:{self._report.ly} RX:{self._report.rx} RY:{self._report.ry}"

    def press(self, key: GamePadKey):
        """
        按下按键（不释放）

        Args:
            key: 按键枚举值
        """
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
        """
        释放按键

        Args:
            key: 按键枚举值
        """
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
        """释放所有按键"""
        self._report.reset()
        self._send_report()

    def click(self, key: GamePadKey, duration_ms: int = 50):
        """
        单击按键（按下并释放）

        Args:
            key: 按键枚举值
            duration_ms: 按下持续时间（毫秒）
        """
        self.press(key)
        self._delay(duration_ms)
        self.release(key)

    def set_stick(self, stick: GamePadKey, x: int, y: int):
        """
        设置摇杆位置

        Args:
            stick: GamePadKey.LS 或 GamePadKey.RS
            x: X轴值 0-255，128为中间
            y: Y轴值 0-255，128为中间
        """
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
        """
        推动摇杆并释放

        Args:
            stick: GamePadKey.LS 或 GamePadKey.RS
            x: X轴值 0-255，128为中间
            y: Y轴值 0-255，128为中间
            duration_ms: 持续时间（毫秒）
        """
        self.set_stick(stick, x, y)
        self._delay(duration_ms)
        self.set_stick(stick, SwitchStick.STICK_CENTER, SwitchStick.STICK_CENTER)

    def push_direction(self, direction: Direction, duration_ms: int = 50):
        """
        推动方向键

        Args:
            direction: 方向枚举值
            duration_ms: 持续时间（毫秒）
        """
        self.click(GamePadKey(direction), duration_ms)

    def reset(self):
        """重置所有按键和摇杆到初始状态"""
        self.release_all()

    def _delay(self, ms: int):
        """精确延迟"""
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
        """等待指定毫秒"""
        time.sleep(ms / 1000.0)


class ImageRecognizer:
    """
    图像识别类
    封装了识图标签的搜索功能
    """

    def __init__(self, capture_source: Optional[int] = None, use_dshow: bool = True):
        """
        Args:
            capture_source: 采集卡设备ID，None则不使用采集卡
            use_dshow: 是否使用DirectShow后端（Windows推荐）
        """
        self.capture_source = capture_source
        self._cap: Optional[cv2.VideoCapture] = None
        self._labels: List[ImgLabel] = []
        self._resolution = (1920, 1080)
        self._use_dshow = use_dshow

        if capture_source is not None:
            self._init_capture(capture_source)

    def _init_capture(self, device_id: int):
        """初始化采集卡"""
        import time
        
        for attempt in range(3):
            if self._use_dshow:
                self._cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
            else:
                self._cap = cv2.VideoCapture(device_id)
            
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._resolution[0])
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._resolution[1])
                self._cap.set(cv2.CAP_PROP_FPS, 60)
                
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    return
            
            if self._cap:
                self._cap.release()
            time.sleep(0.5)
        
        raise RuntimeError(f"Cannot open capture device {device_id} after 3 attempts")
    
    @staticmethod
    def list_capture_devices() -> List[str]:
        """列出所有可用的视频采集设备"""
        try:
            from pygrabber.dshow_graph import FilterGraph
            graph = FilterGraph()
            return graph.get_input_devices()
        except ImportError:
            devices = []
            for i in range(10):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    devices.append(f"Device {i}")
                    cap.release()
            return devices

    def set_resolution(self, width: int, height: int):
        """设置采集分辨率"""
        self._resolution = (width, height)
        if self._cap:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def load_label(self, label: ImgLabel):
        """加载图像标签"""
        self._labels.append(label)

    def load_label_from_file(self, path: str) -> ImgLabel:
        """从 .IL 文件加载标签"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        label = ImgLabel.from_dict(data)
        label.name = path.split("/")[-1].replace(".IL", "")
        if label.image_base64:
            # 解码 base64 图片
            img_data = base64.b64decode(label.image_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            # 缓存解码后的图片
            label._cv_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        self._labels.append(label)
        return label

    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧（从采集卡或屏幕）"""
        if self._cap:
            ret, frame = self._cap.read()
            if ret:
                return frame
        return None

    def search(self, label_name: str, frame: Optional[np.ndarray] = None) -> Tuple[bool, float, Tuple[int, int]]:
        """
        搜索指定标签

        Args:
            label_name: 标签名称
            frame: 要搜索的画面，None则使用采集卡当前帧

        Returns:
            (是否找到, 匹配度0-100, 位置坐标)
        """
        label = None
        for l in self._labels:
            if l.name == label_name:
                label = l
                break

        if label is None:
            raise ValueError(f"Label '{label_name}' not found")

        if frame is None:
            frame = self.get_frame()

        if frame is None:
            raise RuntimeError("No frame available")

        # 获取搜索范围
        h, w = frame.shape[:2]

        # 根据分辨率缩放坐标
        scale_x = w / 1920.0
        scale_y = h / 1080.0

        rx = int(label.range_x * scale_x)
        ry = int(label.range_y * scale_y)
        rw = int(label.range_width * scale_x)
        rh = int(label.range_height * scale_y)

        # 确保范围有效
        rx = max(0, min(rx, w))
        ry = max(0, min(ry, h))
        rw = min(rw, w - rx)
        rh = min(rh, h - ry)

        if rw <= 0 or rh <= 0:
            return False, 0, (0, 0)

        # 裁剪搜索区域
        search_area = frame[ry:ry+rh, rx:rx+rw]

        # 获取目标图片
        if hasattr(label, '_cv_image') and label._cv_image is not None:
            target = label._cv_image
        else:
            return False, 0, (0, 0)

        # 模板匹配
        result = cv2.matchTemplate(search_area, target, label.search_method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 根据方法类型确定最佳匹配
        if label.search_method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            match_val = 1.0 - min_val
            match_loc = min_loc
        else:
            match_val = max_val
            match_loc = max_loc

        match_degree = match_val * 100

        # 计算在原图中的位置
        abs_x = rx + match_loc[0] + target.shape[1] // 2
        abs_y = ry + match_loc[1] + target.shape[0] // 2

        found = match_degree >= label.threshold

        return found, match_degree, (abs_x, abs_y)

    def search_all(self, frame: Optional[np.ndarray] = None) -> dict:
        """
        搜索所有标签

        Returns:
            {标签名: (是否找到, 匹配度, 位置)}
        """
        if frame is None:
            frame = self.get_frame()

        results = {}
        for label in self._labels:
            results[label.name] = self.search(label.name, frame)
        return results

    def release(self):
        """释放资源"""
        if self._cap:
            self._cap.release()
            self._cap = None


class EasyConScript:
    """
    高级脚本接口，结合按键控制和图像识别
    """

    def __init__(self, controller: EasyConController, recognizer: Optional[ImageRecognizer] = None):
        self.controller = controller
        self.recognizer = recognizer

    def wait_for(self, label_name: str, timeout_ms: int = 10000, check_interval_ms: int = 100) -> bool:
        """
        等待指定标签出现

        Args:
            label_name: 标签名称
            timeout_ms: 超时时间（毫秒）
            check_interval_ms: 检查间隔（毫秒）

        Returns:
            是否在超时前找到
        """
        if self.recognizer is None:
            raise RuntimeError("ImageRecognizer not provided")

        start = time.time()
        timeout_sec = timeout_ms / 1000.0

        while time.time() - start < timeout_sec:
            found, degree, pos = self.recognizer.search(label_name)
            if found:
                return True
            time.sleep(check_interval_ms / 1000.0)

        return False

    def click_when_found(self, label_name: str, key: GamePadKey, timeout_ms: int = 10000) -> bool:
        """
        找到标签后点击按键

        Args:
            label_name: 标签名称
            key: 要点击的按键
            timeout_ms: 超时时间（毫秒）

        Returns:
            是否成功点击
        """
        if self.wait_for(label_name, timeout_ms):
            self.controller.click(key)
            return True
        return False

    def loop_until_found(self, label_name: str, action: Callable, interval_ms: int = 1000):
        """
        循环执行动作直到找到标签

        Args:
            label_name: 标签名称
            action: 要执行的动作函数
            interval_ms: 动作间隔（毫秒）
        """
        while True:
            found, _, _ = self.recognizer.search(label_name)
            if found:
                break
            action()
            time.sleep(interval_ms / 1000.0)


# ========== 便捷函数 ==========

def create_controller(port: Optional[str] = None, debug: bool = False) -> EasyConController:
    """
    创建并连接控制器的便捷函数

    Example:
        ns = create_controller()  # 自动搜索并连接
        ns = create_controller("COM3")  # 连接指定串口
    """
    ctrl = EasyConController()
    ctrl.set_debug(debug)
    if not ctrl.connect(port):
        raise ConnectionError("Failed to connect to EasyCon device")
    return ctrl


def create_recognizer(device_id: int = 0) -> ImageRecognizer:
    """
    创建图像识别器的便捷函数

    Args:
        device_id: 采集卡设备ID
    """
    return ImageRecognizer(device_id)

