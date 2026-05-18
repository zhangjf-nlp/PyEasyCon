import time
import json
import base64
import os
from typing import Optional, Callable, Any

import cv2
import numpy as np

from .controller import EasyConController
from .protocol import GamePadKey


class ScriptContext:
    def __init__(
        self,
        controller: Optional[EasyConController] = None,
        get_frame: Optional[Callable[[], Optional[np.ndarray]]] = None,
        log_func: Optional[Callable[[str], None]] = None,
        is_running_func: Optional[Callable[[], bool]] = None,
        ocr_pokemon_func: Optional[Callable[[], Any]] = None,
        ocr_elevated_func: Optional[Callable[[], Any]] = None,
        ocr_caught_info_func: Optional[Callable[[], Any]] = None,
        ocr_caught_iv_func: Optional[Callable[[], Any]] = None,
        ocr_custom_func: Optional[Callable] = None,
        identify_pokemon_func: Optional[Callable] = None,
        ocr_name_func: Optional[Callable] = None,
        labels_dir: str = "assets/labels",
    ):
        self._controller = controller
        self._get_frame = get_frame
        self._log_func = log_func
        self._is_running_func = is_running_func
        self._ocr_pokemon_func = ocr_pokemon_func
        self._ocr_elevated_func = ocr_elevated_func
        self._ocr_caught_info_func = ocr_caught_info_func
        self._ocr_caught_iv_func = ocr_caught_iv_func
        self._ocr_custom_func = ocr_custom_func
        self._identify_pokemon_func = identify_pokemon_func
        self._ocr_name_func = ocr_name_func
        self._labels_dir = labels_dir

        self._button_map = {
            'A': GamePadKey.A, 'B': GamePadKey.B, 'X': GamePadKey.X, 'Y': GamePadKey.Y,
            'L': GamePadKey.L, 'R': GamePadKey.R, 'ZL': GamePadKey.ZL, 'ZR': GamePadKey.ZR,
            'PLUS': GamePadKey.PLUS, 'MINUS': GamePadKey.MINUS,
            'HOME': GamePadKey.HOME, 'CAPTURE': GamePadKey.CAPTURE,
            'UP': GamePadKey.TOP, 'DOWN': GamePadKey.DOWN,
            'LEFT': GamePadKey.LEFT, 'RIGHT': GamePadKey.RIGHT,
        }

    def press(self, button: str, duration_ms: int = 50):
        if self._controller and self._controller.is_connected:
            key = self._button_map.get(button.upper())
            if key:
                self._controller.click(key, duration_ms)

    def hold(self, button: str):
        if self._controller and self._controller.is_connected:
            key = self._button_map.get(button.upper())
            if key:
                self._controller.press(key)

    def release(self, button: str):
        if self._controller and self._controller.is_connected:
            key = self._button_map.get(button.upper())
            if key:
                self._controller.release(key)

    def lstick(self, x: int, y: int, duration_ms: int = 50):
        if self._controller and self._controller.is_connected:
            self._controller.lstick(x, y, duration_ms)

    def capture(self):
        if self._controller and self._controller.is_connected:
            self._controller.capture()

    def wait(self, ms: int):
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if self._is_running_func and not self._is_running_func():
                raise SystemExit("脚本已停止")
            time.sleep(0.05)

    def log(self, msg: str):
        if self._log_func:
            self._log_func(msg)

    def is_running(self) -> bool:
        if self._is_running_func:
            return self._is_running_func()
        return False

    def get_frame(self) -> Optional[np.ndarray]:
        if self._get_frame:
            return self._get_frame()
        return None

    def search_label(self, label_name: str, threshold: int = 80, debug: bool = False):
        try:
            label_path = os.path.join(self._labels_dir, f"{label_name}.IL")
            if not os.path.exists(label_path):
                return 0 if threshold == -1 else False

            with open(label_path, 'r', encoding='utf-8') as f:
                label_data = json.load(f)

            frame = self.get_frame()
            if frame is None:
                return 0 if threshold == -1 else False

            if not label_data.get('ImgBase64'):
                return 0 if threshold == -1 else False

            img_bytes = base64.b64decode(label_data['ImgBase64'])
            nparr = np.frombuffer(img_bytes, np.uint8)
            template = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            rx = label_data.get('RangeX', 0)
            ry = label_data.get('RangeY', 0)
            rw = label_data.get('RangeWidth', frame.shape[1])
            rh = label_data.get('RangeHeight', frame.shape[0])
            rx = max(0, rx); ry = max(0, ry)
            rw = min(rw, frame.shape[1] - rx); rh = min(rh, frame.shape[0] - ry)
            roi = frame[ry:ry + rh, rx:rx + rw]

            search_method = label_data.get('searchMethod', 5)

            if search_method == 0:
                result = cv2.matchTemplate(roi, template, cv2.TM_SQDIFF)
                mn, mx, _, _ = cv2.minMaxLoc(result)
                match_degree = (1.0 - mn) * 100.0
            elif search_method == 1:
                result = cv2.matchTemplate(roi, template, cv2.TM_SQDIFF_NORMED)
                mn, mx, _, _ = cv2.minMaxLoc(result)
                match_degree = (1.0 - mn) * 100.0
            elif search_method in (2, 3):
                mode = cv2.TM_CCORR if search_method == 2 else cv2.TM_CCORR_NORMED
                result = cv2.matchTemplate(roi, template, mode)
                mn, mx, _, _ = cv2.minMaxLoc(result)
                match_degree = mx * 100.0
            else:
                mode = cv2.TM_CCOEFF if search_method == 4 else cv2.TM_CCOEFF_NORMED
                result = cv2.matchTemplate(roi, template, mode)
                mn, mx, _, _ = cv2.minMaxLoc(result)
                match_degree = (mx + 1.0) * 50.0

            found = match_degree >= threshold
            degree_int = int(match_degree)

            if debug:
                marker = "*" if found else " "
                self.log(f"  [{marker}] {label_name} = {match_degree:.1f}% (threshold={threshold})")
            return degree_int if threshold == -1 else found

        except Exception as e:
            if debug:
                self.log(f"  [label] {label_name} -> 错误: {e}")
            return 0 if threshold == -1 else False

    def ocr_pokemon(self):
        if self._ocr_pokemon_func:
            return self._ocr_pokemon_func()
        return None

    def ocr_elevated(self):
        if self._ocr_elevated_func:
            return self._ocr_elevated_func()
        return None

    def ocr_caught_info(self):
        if self._ocr_caught_info_func:
            return self._ocr_caught_info_func()
        return None

    def ocr_caught_iv(self):
        if self._ocr_caught_iv_func:
            return self._ocr_caught_iv_func()
        return None

    def ocr_custom(self, image, prompt: str, model_type: str = None):
        if self._ocr_custom_func:
            return self._ocr_custom_func(image, prompt, model_type)
        return None

    def identify_pokemon(self, candidates=None, threshold=0.0):
        if self._identify_pokemon_func:
            return self._identify_pokemon_func(candidates=candidates, threshold=threshold)
        return None, 0.0, False

    def ocr_name(self, candidates=None):
        if self._ocr_name_func:
            return self._ocr_name_func(candidates=candidates)
        return None