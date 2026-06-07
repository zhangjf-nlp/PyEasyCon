import json
import base64
import os
import time
import threading
from typing import Optional, Callable, Any

import cv2
import numpy as np

from .controller import EasyConController, sleep
from .protocol import GamePadKey


class _HoldContext:
    def __init__(self, ctx: "ScriptContext", button: str):
        self._ctx = ctx
        self._button = button

    def __enter__(self):
        pass

    def __exit__(self, *args):
        self._ctx.release(self._button)


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
        ocr_taken_item_func: Optional[Callable] = None,
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
        self._ocr_taken_item_func = ocr_taken_item_func
        self._identify_pokemon_func = identify_pokemon_func
        self._ocr_name_func = ocr_name_func
        self._labels_dir = labels_dir
        self._label_cache = {}

        # 屏幕录制
        self._recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._record_frames: list = []

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
        return _HoldContext(self, button)

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

    def _load_label(self, label_name):
        label_path = os.path.join(self._labels_dir, f"{label_name}.IL")
        if not os.path.exists(label_path):
            self._label_cache[label_name] = None
            return None

        with open(label_path, 'r', encoding='utf-8') as f:
            label_data = json.load(f)

        if not label_data.get('ImgBase64'):
            self._label_cache[label_name] = None
            return None

        img_bytes = base64.b64decode(label_data['ImgBase64'])
        nparr = np.frombuffer(img_bytes, np.uint8)
        cached = {
            'template': cv2.imdecode(nparr, cv2.IMREAD_COLOR),
            'rx': label_data.get('RangeX', 0),
            'ry': label_data.get('RangeY', 0),
            'rw': label_data.get('RangeWidth'),
            'rh': label_data.get('RangeHeight'),
            'search_method': label_data.get('searchMethod', 5),
        }
        self._label_cache[label_name] = cached
        return cached

    def search_label(self, label_name: str, threshold: int = 80, debug: bool = False):
        try:
            cached = self._label_cache.get(label_name)
            if cached is None:
                if label_name in self._label_cache:
                    return 0 if threshold == -1 else False
                cached = self._load_label(label_name)
                if cached is None:
                    return 0 if threshold == -1 else False

            frame = self.get_frame()
            if frame is None:
                return 0 if threshold == -1 else False

            template = cached['template']
            rx = max(0, cached['rx'])
            ry = max(0, cached['ry'])
            rw = cached['rw'] if cached['rw'] is not None else frame.shape[1]
            rh = cached['rh'] if cached['rh'] is not None else frame.shape[0]
            rw = min(rw, frame.shape[1] - rx)
            rh = min(rh, frame.shape[0] - ry)
            roi = frame[ry:ry + rh, rx:rx + rw]

            search_method = cached['search_method']

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

    def ocr_taken_item(self, frame):
        if self._ocr_taken_item_func:
            return self._ocr_taken_item_func(frame)
        return None

    def identify_pokemon(self, candidates=None, threshold=0.0):
        if self._identify_pokemon_func:
            return self._identify_pokemon_func(candidates=candidates, threshold=threshold)
        return None, 0.0, False

    def ocr_name(self, candidates=None):
        if self._ocr_name_func:
            return self._ocr_name_func(candidates=candidates)
        return None

    def save_ocr_screenshot(self, save_path: str, screen_type: str):
        frame = self.get_frame()
        if frame is None:
            return
        from vision.ocr import get_all_roi_boxes

        _GROUP_MAP = {
            "ELEVATED": "Elevated",
            "CAUGHT_INFO": "Caught",
            "CAUGHT_IV": "CaughtIV",
            "APPEARED": "Appeared",
        }
        group = _GROUP_MAP.get(screen_type)
        if group is None:
            return

        all_boxes = get_all_roi_boxes()
        boxes = [b for b in all_boxes if b['group'] == group]

        h, w = frame.shape[:2]
        sx = w / 1920.0
        sy = h / 1080.0
        annotated = frame.copy()
        for b in boxes:
            x, y, rw, rh = b['roi']
            x1, y1 = int(x * sx), int(y * sy)
            x2, y2 = int((x + rw) * sx), int((y + rh) * sy)
            color = b['color']
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, b['label'], (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cv2.imwrite(save_path, annotated)

    def screen_record_start(self):
        """开始录制GUI显示的游戏画面"""
        if self._recording:
            return
        self._recording = True
        self._record_frames = []
        self._record_thread = threading.Thread(target=self._record_worker, daemon=True)
        self._record_thread.start()

    def _record_worker(self):
        """录制线程：持续抓取画面帧"""
        while self._recording:
            frame = self.get_frame()
            if frame is not None:
                self._record_frames.append(frame.copy())
            time.sleep(1 / 30.0)

    def screen_record_end(self):
        """结束录制"""
        self._recording = False
        if self._record_thread:
            self._record_thread.join(timeout=2.0)
            self._record_thread = None

    def screen_record_save(self, save_path: str = None):
        """保存录制的视频，默认保存至 screen_record/{timestamp}.mp4"""
        if not self._record_frames:
            self.log("没有录制帧可保存")
            return

        if save_path is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_path = f"screen_record/{ts}.mp4"

        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        h, w = self._record_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(save_path, fourcc, 30.0, (w, h))

        for frame in self._record_frames:
            out.write(frame)
        out.release()

        self.log(f"视频已保存: {save_path} ({len(self._record_frames)} 帧)")
        self._record_frames.clear()