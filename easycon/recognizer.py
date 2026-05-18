import base64
import json
import time
from typing import Optional, List, Callable, Tuple

import cv2
import numpy as np

from .image_label import ImgLabel
from .protocol import GamePadKey
from .controller import EasyConController


class ImageRecognizer:
    def __init__(self, capture_source: Optional[int] = None, use_dshow: bool = True):
        self.capture_source = capture_source
        self._cap: Optional[cv2.VideoCapture] = None
        self._labels: List[ImgLabel] = []
        self._resolution = (1920, 1080)
        self._use_dshow = use_dshow

        if capture_source is not None:
            self._init_capture(capture_source)

    def _init_capture(self, device_id: int):
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
        self._resolution = (width, height)
        if self._cap:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def load_label(self, label: ImgLabel):
        self._labels.append(label)

    def load_label_from_file(self, path: str) -> ImgLabel:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        label = ImgLabel.from_dict(data)
        label.name = path.split("/")[-1].replace(".IL", "")
        if label.image_base64:
            img_data = base64.b64decode(label.image_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            label._cv_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        self._labels.append(label)
        return label

    def get_frame(self) -> Optional[np.ndarray]:
        if self._cap:
            ret, frame = self._cap.read()
            if ret:
                return frame
        return None

    def search(self, label_name: str, frame: Optional[np.ndarray] = None) -> Tuple[bool, float, Tuple[int, int]]:
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

        h, w = frame.shape[:2]

        scale_x = w / 1920.0
        scale_y = h / 1080.0

        rx = int(label.range_x * scale_x)
        ry = int(label.range_y * scale_y)
        rw = int(label.range_width * scale_x)
        rh = int(label.range_height * scale_y)

        rx = max(0, min(rx, w - 1))
        ry = max(0, min(ry, h - 1))
        rw = max(1, min(rw, w - rx))
        rh = max(1, min(rh, h - ry))

        search_region = frame[ry:ry + rh, rx:rx + rw]

        if hasattr(label, '_cv_image') and label._cv_image is not None:
            target = label._cv_image
        elif label.image_base64:
            img_data = base64.b64decode(label.image_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            target = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            raise ValueError(f"Label '{label_name}' has no image data")

        if target is None or target.size == 0:
            raise ValueError(f"Label '{label_name}' image is invalid")

        th, tw = target.shape[:2]
        if search_region.shape[0] < th or search_region.shape[1] < tw:
            return False, 0.0, (0, 0)

        result = cv2.matchTemplate(search_region, target, label.search_method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if label.search_method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
            match_val = 1.0 - min_val
            match_loc = min_loc
        else:
            match_val = max_val
            match_loc = max_loc

        match_degree = match_val * 100

        abs_x = rx + match_loc[0] + target.shape[1] // 2
        abs_y = ry + match_loc[1] + target.shape[0] // 2

        found = match_degree >= label.threshold

        return found, match_degree, (abs_x, abs_y)

    def search_all(self, frame: Optional[np.ndarray] = None) -> dict:
        if frame is None:
            frame = self.get_frame()

        results = {}
        for label in self._labels:
            results[label.name] = self.search(label.name, frame)
        return results

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None


class EasyConScript:
    def __init__(self, controller: EasyConController, recognizer: Optional[ImageRecognizer] = None):
        self.controller = controller
        self.recognizer = recognizer

    def wait_for(self, label_name: str, timeout_ms: int = 10000, check_interval_ms: int = 100) -> bool:
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
        if self.wait_for(label_name, timeout_ms):
            self.controller.click(key)
            return True
        return False

    def loop_until_found(self, label_name: str, action: Callable, interval_ms: int = 1000):
        while True:
            found, _, _ = self.recognizer.search(label_name)
            if found:
                break
            action()
            time.sleep(interval_ms / 1000.0)