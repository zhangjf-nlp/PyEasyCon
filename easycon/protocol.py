from enum import IntEnum


class GamePadKey(IntEnum):
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
    LS = 32
    RS = 33


class Direction(IntEnum):
    UP = GamePadKey.TOP
    UP_RIGHT = GamePadKey.TOP_RIGHT
    RIGHT = GamePadKey.RIGHT
    DOWN_RIGHT = GamePadKey.DOWN_RIGHT
    DOWN = GamePadKey.DOWN
    DOWN_LEFT = GamePadKey.DOWN_LEFT
    LEFT = GamePadKey.LEFT
    UP_LEFT = GamePadKey.TOP_LEFT


class SwitchButton(IntEnum):
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
    TOP = 0x00
    TOP_RIGHT = 0x01
    RIGHT = 0x02
    BOTTOM_RIGHT = 0x03
    BOTTOM = 0x04
    BOTTOM_LEFT = 0x05
    LEFT = 0x06
    TOP_LEFT = 0x07
    CENTER = 0x08


class SwitchStick:
    STICK_CENTER = 128
    STICK_MAX = 255
    STICK_MIN = 0


class SwitchReport:
    def __init__(self):
        self.button: int = 0
        self.hat: int = SwitchHAT.CENTER
        self.lx: int = SwitchStick.STICK_CENTER
        self.ly: int = SwitchStick.STICK_CENTER
        self.rx: int = SwitchStick.STICK_CENTER
        self.ry: int = SwitchStick.STICK_CENTER

    def reset(self):
        self.button = 0
        self.hat = SwitchHAT.CENTER
        self.lx = SwitchStick.STICK_CENTER
        self.ly = SwitchStick.STICK_CENTER
        self.rx = SwitchStick.STICK_CENTER
        self.ry = SwitchStick.STICK_CENTER

    def get_bytes(self) -> bytes:
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
        r = SwitchReport()
        r.button = self.button
        r.hat = self.hat
        r.lx = self.lx
        r.ly = self.ly
        r.rx = self.rx
        r.ry = self.ry
        return r