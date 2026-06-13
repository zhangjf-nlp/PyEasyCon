"""
Pokemon OCR Module - 宝可梦信息 OCR 识别模块
通过 vision.vlm 的 VL 模型进行图像识别

ROI 坐标基于 1920×1080 (采集卡直出)
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

from .vlm import call_vlm_func, get_provider, get_current_model_type


SRC_WIDTH = 1920
SRC_HEIGHT = 1080

# 25种性格
NATURES = [
    "Adamant", "Bashful", "Bold", "Brave", "Calm", "Careful", "Docile",
    "Gentle", "Hardy", "Hasty", "Impish", "Jolly", "Lax", "Lonely",
    "Mild", "Modest", "Naive", "Naughty", "Quiet", "Quirky", "Rash",
    "Relaxed", "Sassy", "Serious", "Timid"
]

ROI = Tuple[int, int, int, int]


# ==================== OCRTask / ScreenOCRTask ====================

@dataclass
class OCRTask:
    label: str
    roi: ROI
    func: Callable[[np.ndarray], Any]


@dataclass
class ScreenOCRTask:
    screen_type: str
    tasks: List[OCRTask]

    def run(self, image: np.ndarray, **kwargs) -> Dict[str, object]:
        """并行执行所有 OCR 任务，返回平铺字典。**kwargs 传递给每个 func。"""
        flat_tasks = [
            (t.label, crop_roi(image, t.roi), lambda img, f=t.func: f(img, **kwargs) if kwargs else f(img))
            for t in self.tasks
        ]
        return parallel_ocr(flat_tasks)

    def save_annotated(self, image: np.ndarray, save_path: str) -> None:
        """保存带 ROI 标注的截图"""
        h, w = image.shape[:2]
        sx = w / SRC_WIDTH
        sy = h / SRC_HEIGHT
        annotated = image.copy()
        colors = [(255, 255, 0), (0, 255, 255), (255, 0, 255), (0, 255, 0)]
        for i, t in enumerate(self.tasks):
            x, y, rw, rh = t.roi
            x1, y1 = int(x * sx), int(y * sy)
            x2, y2 = int((x + rw) * sx), int((y + rh) * sy)
            color = colors[i % len(colors)]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, t.label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        cv2.imwrite(save_path, annotated)


# ==================== OCR 单项识别 ====================

def ocr_digits(roi_image: np.ndarray) -> Optional[int]:
    result = call_vlm_func(roi_image, "识别图片中的数字，只输出数字本身，不要输出其他任何内容。数字可能包含斜杠（如 26/31）。")
    if result:
        text = result.replace(' ', '').strip().rstrip(".")
        if '/' in text:
            text = text.split('/')[1]
        try:
            return int(text)
        except ValueError:
            return None
    return None


def ocr_nature(roi_image: np.ndarray) -> Optional[str]:
    nature_list = "\n".join([f"- {n}" for n in NATURES])
    prompt = f"识别图片中的宝可梦性格（Nature）。\n性格只能是以下25种之一：\n{nature_list}\n只输出性格名称，首字母大写，不要输出其他任何内容。"
    result = call_vlm_func(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None


def ocr_ability(roi_image: np.ndarray) -> Optional[str]:
    prompt = "识别图片中的宝可梦特性（Ability）名称。只输出特性名称，全部大写，保留单词之间的空格，不要输出其他任何内容。"
    result = call_vlm_func(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None


def ocr_text(roi_image: np.ndarray) -> Optional[str]:
    result = call_vlm_func(roi_image, "识别图片中的文字，只输出文字内容本身，不要添加任何额外描述或格式。", max_tokens=128, temperature=0.1)
    return result.strip() if result else None


def ocr_pokemon_name(roi_image: np.ndarray, candidates: Optional[List[str]] = None, debug: bool = False) -> Optional[str]:
    if not candidates:
        return None
    prompt = (
        "Which Pokemon is in this image? Choose from: "
        + ", ".join(candidates)
        + ". Reply with ONLY the English name, or NONE if none match."
    )
    result = call_vlm_func(roi_image, prompt, max_tokens=128, temperature=0.2)
    return result.strip() if result else None


# ==================== 内部辅助 ====================

def crop_roi(image, roi):
    x, y, w, h = roi
    return image[y:y+h, x:x+w]


def parallel_ocr(tasks: List[Tuple[str, np.ndarray, callable]]) -> Dict[str, object]:
    """
    并行执行多个 OCR 任务。
    tasks: [(key, roi_image, ocr_function), ...]
    """
    provider = get_provider(get_current_model_type())
    max_workers = min(provider.max_concurrency, len(tasks))
    raw: Dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(ocr_func, img): key for key, img, ocr_func in tasks}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val = fut.result()
                raw[key] = val if val is not None else ""
            except Exception:
                raw[key] = ""
    results: Dict[str, object] = {}
    for key, _, _ in tasks:
        if key in raw:
            results[key] = raw[key]
    return results


# ==================== OCR 技能注册表 (ROI 直接内联) ====================

ocr_skills: Dict[str, ScreenOCRTask] = {
    "ELEVATED": ScreenOCRTask(
        screen_type="ELEVATED",
        tasks=[
            OCRTask('level', (360, 876, 138, 124), ocr_digits),
            OCRTask('hp', (1545, 48, 152, 97), ocr_digits),
            OCRTask('attack', (1545, 145, 152, 97), ocr_digits),
            OCRTask('defense', (1545, 242, 152, 97), ocr_digits),
            OCRTask('sp_atk', (1545, 339, 152, 97), ocr_digits),
            OCRTask('sp_def', (1545, 436, 152, 97), ocr_digits),
            OCRTask('speed', (1545, 533, 152, 97), ocr_digits),
        ]
    ),
    "CAUGHT_INFO": ScreenOCRTask(
        screen_type="CAUGHT_INFO",
        tasks=[
            OCRTask('level', (262, 124, 108, 85), ocr_digits),
            OCRTask('nature', (222, 746, 741, 97), ocr_nature),
        ]
    ),
    "CAUGHT_IV": ScreenOCRTask(
        screen_type="CAUGHT_IV",
        tasks=[
            OCRTask('level', (262, 124, 108, 85), ocr_digits),
            OCRTask('hp', (1439, 140, 288, 72), ocr_digits),
            OCRTask('attack', (1600, 258, 127, 72), ocr_digits),
            OCRTask('defense', (1600, 343, 127, 72), ocr_digits),
            OCRTask('sp_atk', (1600, 429, 127, 72), ocr_digits),
            OCRTask('sp_def', (1600, 514, 127, 72), ocr_digits),
            OCRTask('speed', (1600, 599, 127, 72), ocr_digits),
            OCRTask('ability', (635, 853, 529, 78), ocr_ability),
        ]
    ),
    "TAKEN_ITEM": ScreenOCRTask(
        screen_type="TAKEN_ITEM",
        tasks=[
            OCRTask('text', (208, 774, 1485, 228), ocr_text),
        ]
    ),
    "POKEMON_NAME": ScreenOCRTask(
        screen_type="POKEMON_NAME",
        tasks=[
            OCRTask('name', (300, 135, 400, 55), ocr_pokemon_name),
        ]
    ),
    "TRAINER_CARD": ScreenOCRTask(
        screen_type="TRAINER_CARD",
        tasks=[
            OCRTask('tid', (1330, 115, 230, 100), ocr_text),
        ]
    ),
}
