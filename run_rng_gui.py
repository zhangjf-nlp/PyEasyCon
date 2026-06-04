# -*- coding: utf-8 -*-
"""
RNG 配置 GUI —— 基于 pygame 的乱数配置界面
通过 run_rng.bat 启动，不依赖 tkinter
"""

import sys
import os
import json
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Callable
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from pygame.locals import *

from rng.config import RNGConfig, RNGSlot, GameSettings, SessionState
from rng.tenlines_utils import (
    calibration as calibration_api,
    get_encounter_species_list,
    get_species_id,
    get_species_name,
    get_species_en_name,
    _load_frlg_encounters,
)
from easycon.config import get as config_get

# ── 常量 ──────────────────────────────────────────────
GAME_OPTIONS = {"火红": "fr_nx", "叶绿": "lg_nx"}

STATIC_CATEGORIES = ["Gift", "Game Corner", "Stationary"]
WILD_CATEGORIES = ["Grass", "Surfing", "SuperRod", "GoodRod", "OldRod"]

METHOD_OPTIONS = {
    "Static": {"categories": STATIC_CATEGORIES, "rng_method": "Static 1"},
    "Wild": {"categories": WILD_CATEGORIES, "rng_method": "All Wild Methods"},
}

DEFAULT_SETTINGS = "Mono | Help | Seed Button: Start | Extra Button: None"

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "rng_logs", "latest.json")

# 颜色
C_BG = (45, 45, 48)
C_PANEL = (55, 55, 58)
C_TEXT = (220, 220, 220)
C_TEXT_DIM = (120, 120, 120)
C_ACCENT = (70, 130, 200)
C_WHITE = (255, 255, 255)
C_BLACK = (0, 0, 0)
C_RED = (220, 80, 80)
C_GREEN = (80, 180, 80)
C_INPUT_BG = (40, 40, 44)
C_INPUT_BORDER = (80, 80, 85)
C_INPUT_FOCUS = (70, 130, 200)
C_BTN_HOVER = (75, 140, 210)
C_DROPDOWN_BG = (50, 50, 55)
C_DROPDOWN_HOVER = (70, 130, 200)
C_SUCCESS = (80, 200, 80)
C_WARNING = (220, 180, 0)

# ── 辅助函数 ──────────────────────────────────────────

def _get_all_locations() -> dict:
    encounters = _load_frlg_encounters()
    cat_to_locs = {}
    for (loc, cat), data in encounters.items():
        if cat not in cat_to_locs:
            cat_to_locs[cat] = set()
        cat_to_locs[cat].add(loc)
    for cat in cat_to_locs:
        cat_to_locs[cat] = sorted(cat_to_locs[cat])
    return cat_to_locs


def _read_calibration_limits():
    return {
        "seed_ms_min": config_get("rng.calibration.seed_ms_min", 33000),
        "seed_ms_max": config_get("rng.calibration.seed_ms_max", 72000),
        "tv_ms_min": config_get("rng.calibration.tv_ms_min", 3000),
        "normal_ms_min": config_get("rng.calibration.normal_ms_min", 10000),
    }


# ── pygame GUI 组件 ──────────────────────────────────

_FONT_CACHE = {}
_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "NotoSansCJKsc-Regular.otf")

def _get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """获取中文字体，使用项目内置开源字体（Noto Sans SC）"""
    key = (size, bold)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pygame.font.Font(_FONT_PATH, size)
    return _FONT_CACHE[key]


class TextBox:
    """文本输入框：支持光标移动、选中、复制、粘贴"""
    def __init__(self, x: int, y: int, w: int, h: int, placeholder: str = ""):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = ""
        self.placeholder = placeholder
        self.focused = False
        self.cursor_pos = 0
        self._sel_start = -1
        self._sel_end = -1
        self._cursor_visible = True
        self._cursor_timer = 0
        self._font = _get_font(15)
        self._scroll_x = 0
        self._dragging = False
        self._ctrl_pressed = set()  # 已处理的 Ctrl+key 组合，防止重复触发

    def _get_selection_range(self):
        if self._sel_start == -1 or self._sel_end == -1:
            return None, None
        s = min(self._sel_start, self._sel_end)
        e = max(self._sel_start, self._sel_end)
        return s, e

    def _has_selection(self) -> bool:
        s, e = self._get_selection_range()
        return s is not None and s != e

    def _clear_selection(self):
        self._sel_start = -1
        self._sel_end = -1

    def _delete_selection(self):
        s, e = self._get_selection_range()
        if s is not None and s < e:
            self.text = self.text[:s] + self.text[e:]
            self.cursor_pos = s
            self._clear_selection()

    def _selected_text(self) -> str:
        s, e = self._get_selection_range()
        if s is not None and s < e:
            return self.text[s:e]
        return ""

    def _text_width_to_pos(self, text: str, target_x: float) -> int:
        for i in range(len(text) + 1):
            w = self._font.size(text[:i])[0]
            if w > target_x:
                return i - 1 if i > 0 else 0
        return len(text)

    def _ensure_cursor_visible(self):
        pad = 6
        inner_w = self.rect.width - pad * 2
        cursor_x = self._font.size(self.text[:self.cursor_pos])[0]
        if cursor_x < self._scroll_x:
            self._scroll_x = cursor_x
        elif cursor_x > self._scroll_x + inner_w:
            self._scroll_x = cursor_x - inner_w
        if self._scroll_x < 0:
            self._scroll_x = 0

    def _clipboard_copy(self):
        text = self._selected_text()
        if text:
            try:
                subprocess.run("clip", input=text, text=True, shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

    def _clipboard_paste(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            paste_text = result.stdout
            if paste_text:
                paste_text = paste_text.replace("\n", "").replace("\r", "")
                self._delete_selection()
                self.text = self.text[:self.cursor_pos] + paste_text + self.text[self.cursor_pos:]
                self.cursor_pos += len(paste_text)
                self._ensure_cursor_visible()
        except Exception:
            pass

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.focused = True
                rel_x = event.pos[0] - self.rect.x - 6 + self._scroll_x
                self.cursor_pos = self._text_width_to_pos(self.text, rel_x)
                self._clear_selection()
                self._sel_start = self.cursor_pos
                self._sel_end = self.cursor_pos
                self._dragging = True
                return True
            else:
                self.focused = False
                self._clear_selection()
                self._dragging = False
                return False

        if event.type == MOUSEBUTTONUP:
            self._dragging = False
            return self.focused

        if event.type == MOUSEMOTION and self._dragging:
            rel_x = event.pos[0] - self.rect.x - 6 + self._scroll_x
            self.cursor_pos = self._text_width_to_pos(self.text, rel_x)
            self._sel_end = self.cursor_pos
            self._ensure_cursor_visible()
            return True

        if event.type == KEYUP:
            self._ctrl_pressed.clear()
            return False

        if event.type == KEYDOWN and self.focused:
            mods = pygame.key.get_mods()
            ctrl = mods & KMOD_CTRL
            shift = mods & KMOD_SHIFT

            if ctrl and event.key == K_a:
                if "a" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("a")
                    self._sel_start = 0
                    self._sel_end = len(self.text)
                    self.cursor_pos = len(self.text)
                return True

            if ctrl and event.key == K_c:
                if "c" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("c")
                    self._clipboard_copy()
                return True

            if ctrl and event.key == K_v:
                if "v" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("v")
                    self._clipboard_paste()
                return True

            if ctrl and event.key == K_x:
                if "x" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("x")
                    self._clipboard_copy()
                    self._delete_selection()
                    self._ensure_cursor_visible()
                return True

            if event.key == K_HOME:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    self._sel_end = 0
                else:
                    self._clear_selection()
                self.cursor_pos = 0
                self._scroll_x = 0
                return True
            if event.key == K_END:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    self._sel_end = len(self.text)
                else:
                    self._clear_selection()
                self.cursor_pos = len(self.text)
                self._ensure_cursor_visible()
                return True

            if event.key == K_LEFT:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    if self.cursor_pos > 0:
                        self.cursor_pos -= 1
                    self._sel_end = self.cursor_pos
                else:
                    if self._has_selection():
                        self.cursor_pos = min(self._sel_start, self._sel_end)
                        self._clear_selection()
                    elif self.cursor_pos > 0:
                        self.cursor_pos -= 1
                self._ensure_cursor_visible()
                return True
            if event.key == K_RIGHT:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    if self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                    self._sel_end = self.cursor_pos
                else:
                    if self._has_selection():
                        self.cursor_pos = max(self._sel_start, self._sel_end)
                        self._clear_selection()
                    elif self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                self._ensure_cursor_visible()
                return True

            if event.key == K_BACKSPACE:
                if self._has_selection():
                    self._delete_selection()
                elif self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
                self._ensure_cursor_visible()
                return True

            if event.key == K_DELETE:
                if self._has_selection():
                    self._delete_selection()
                elif self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
                self._ensure_cursor_visible()
                return True

            if event.key in (K_RETURN, K_TAB, K_ESCAPE):
                self.focused = False
                self._clear_selection()
                return True

            if event.unicode and event.unicode.isprintable() and not ctrl:
                self._delete_selection()
                ch = event.unicode
                self.text = self.text[:self.cursor_pos] + ch + self.text[self.cursor_pos:]
                self.cursor_pos += 1
                self._ensure_cursor_visible()
                return True

            return True
        return False

    def update(self, dt: float):
        if self.focused:
            self._cursor_timer += dt
            if self._cursor_timer > 0.5:
                self._cursor_visible = not self._cursor_visible
                self._cursor_timer = 0
        else:
            self._cursor_visible = False

    def draw(self, screen: pygame.Surface):
        border_color = C_INPUT_FOCUS if self.focused else C_INPUT_BORDER
        pygame.draw.rect(screen, C_INPUT_BG, self.rect, border_radius=4)
        pygame.draw.rect(screen, border_color, self.rect, width=2, border_radius=4)

        pad = 6
        clip_rect = pygame.Rect(self.rect.x + pad, self.rect.y + 2,
                                 self.rect.width - pad * 2, self.rect.height - 4)
        screen.set_clip(clip_rect)

        text_x = self.rect.x + pad - self._scroll_x

        if self.text:
            s, e = self._get_selection_range()
            if s is not None and s < e and self.focused:
                pre_w = self._font.size(self.text[:s])[0]
                sel_w = self._font.size(self.text[s:e])[0]
                sel_rect = pygame.Rect(text_x + pre_w, self.rect.y + 4,
                                       sel_w, self.rect.height - 8)
                pygame.draw.rect(screen, (70, 130, 220), sel_rect)

            txt = self._font.render(self.text, True, C_TEXT)
            screen.blit(txt, (text_x, self.rect.centery - txt.get_height() // 2))
        else:
            show = "" if self.focused else self.placeholder
            color = C_TEXT if self.focused else C_TEXT_DIM
            txt = self._font.render(show, True, color)
            screen.blit(txt, (text_x, self.rect.centery - txt.get_height() // 2))

        if self.focused and self._cursor_visible:
            cursor_x = text_x + self._font.size(self.text[:self.cursor_pos])[0]
            pygame.draw.line(screen, C_TEXT,
                             (cursor_x, self.rect.y + 5),
                             (cursor_x, self.rect.bottom - 5), 2)

        screen.set_clip(None)

    def get_value(self) -> str:
        return self.text.strip()

    def clear(self):
        self.text = ""
        self.cursor_pos = 0
        self._scroll_x = 0
        self._clear_selection()
        self.focused = False


class ComboBox:
    """可搜索下拉选择框：支持文本输入 + 前缀匹配过滤 + 滚轮滚动"""
    def __init__(self, x: int, y: int, w: int, h: int, options: list = None,
                 screen_height: int = 600, placeholder: str = ""):
        self.rect = pygame.Rect(x, y, w, h)
        self._all_options = options or []
        self.options = list(self._all_options)  # 当前过滤后的选项
        self._filter_text = ""  # 用户输入的过滤文本
        self.selected_index = -1  # 在 _all_options 中的索引
        self._opened = False
        self._scroll_offset = 0
        self._font = _get_font(14)
        self._on_change: Optional[Callable] = None
        self._screen_height = screen_height
        self.placeholder = placeholder
        # 文本输入状态
        self._editing = False
        self._cursor_visible = True
        self._cursor_timer = 0

    def set_options(self, options: list, default_index: int = -1):
        self._all_options = options or []
        self._filter_text = ""
        self._apply_filter()
        self.selected_index = default_index
        self._opened = False
        self._scroll_offset = 0
        self._editing = False

    def set_on_change(self, callback: Callable):
        self._on_change = callback

    def get_value(self) -> str:
        if 0 <= self.selected_index < len(self._all_options):
            return self._all_options[self.selected_index]
        if self._filter_text.strip():
            return self._filter_text.strip()
        return ""

    def clear(self):
        self._filter_text = ""
        self.selected_index = -1
        self._opened = False
        self._editing = False
        self._apply_filter()

    def _apply_filter(self):
        """根据 _filter_text 过滤选项"""
        ft = self._filter_text.lower()
        if ft:
            self.options = [o for o in self._all_options if ft in o.lower()]
        else:
            self.options = list(self._all_options)

    def _get_max_visible(self) -> int:
        item_h = self._font.get_height() + 6
        available = self._screen_height - self.rect.bottom - 6
        return max(1, min(8, len(self.options), available // item_h))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if not self._opened:
                    self._opened = True
                    self._editing = True
                    self._filter_text = ""
                    self._apply_filter()
                    self._scroll_offset = 0
                else:
                    self._opened = False
                    self._editing = False
                return True
            elif self._opened:
                # 检查是否点击了下拉列表中的某项
                item_h = self._font.get_height() + 6
                max_visible = self._get_max_visible()
                for i, opt in enumerate(self.options):
                    item_y = self.rect.bottom + 2 + (i - self._scroll_offset) * item_h
                    if 0 <= i - self._scroll_offset < max_visible:
                        item_rect = pygame.Rect(self.rect.x, item_y, self.rect.width, item_h)
                        if item_rect.collidepoint(event.pos):
                            self._select_by_filtered_index(i)
                            return True
                self._opened = False
                self._editing = False
                return True
        if event.type == MOUSEWHEEL and self._opened:
            self._scroll_offset = max(0, self._scroll_offset - event.y)
            return True
        if event.type == KEYDOWN and self._opened:
            if event.key == K_ESCAPE:
                self._opened = False
                self._editing = False
                return True
            if event.key == K_RETURN:
                if self.options:
                    self._select_by_filtered_index(0)
                self._opened = False
                self._editing = False
                return True
            if event.key == K_DOWN:
                self._scroll_offset = min(
                    self._scroll_offset + 1,
                    max(0, len(self.options) - self._get_max_visible())
                )
                return True
            if event.key == K_UP:
                self._scroll_offset = max(0, self._scroll_offset - 1)
                return True
            if event.key == K_BACKSPACE:
                self._filter_text = self._filter_text[:-1]
                self._apply_filter()
                self._scroll_offset = 0
                return True
            if event.unicode and event.unicode.isprintable():
                self._filter_text += event.unicode
                self._apply_filter()
                self._scroll_offset = 0
                return True
        return False

    def _select_by_filtered_index(self, filtered_idx: int):
        """根据过滤列表中的索引，找到在 _all_options 中的实际索引并选中"""
        opt = self.options[filtered_idx]
        try:
            self.selected_index = self._all_options.index(opt)
        except ValueError:
            self.selected_index = -1
        self._filter_text = ""
        self._apply_filter()
        self._opened = False
        self._editing = False
        self._scroll_offset = 0
        if self._on_change:
            self._on_change()

    def update(self, dt: float):
        if self._editing:
            self._cursor_timer += dt
            if self._cursor_timer > 0.5:
                self._cursor_visible = not self._cursor_visible
                self._cursor_timer = 0
        else:
            self._cursor_visible = False

    def _display_text(self) -> str:
        """获取要显示的文本"""
        if self._opened:
            return self._filter_text
        if self.selected_index >= 0:
            return self._all_options[self.selected_index]
        return ""

    def draw(self, screen: pygame.Surface):
        """仅绘制主框体（不含下拉列表）"""
        border_color = C_INPUT_FOCUS if self._opened else C_INPUT_BORDER
        pygame.draw.rect(screen, C_INPUT_BG, self.rect, border_radius=4)
        pygame.draw.rect(screen, border_color, self.rect, width=2, border_radius=4)

        display = self._display_text()
        if display:
            txt = self._font.render(display, True, C_TEXT)
        elif self._editing:
            txt = self._font.render("", True, C_TEXT)
        else:
            txt = self._font.render(self.placeholder, True, C_TEXT_DIM)

        text_rect = txt.get_rect(midleft=(self.rect.x + 8, self.rect.centery))
        screen.blit(txt, text_rect)

        if self._editing and self._cursor_visible:
            cursor_x = text_rect.right + 2
            pygame.draw.line(screen, C_TEXT,
                             (cursor_x, self.rect.y + 6),
                             (cursor_x, self.rect.bottom - 6), 2)

        # 下拉箭头
        arrow = self._font.render("▼", True, C_TEXT_DIM)
        screen.blit(arrow, (self.rect.right - 22, self.rect.centery - arrow.get_height() // 2))

    def draw_overlay(self, screen: pygame.Surface):
        """绘制下拉列表（在所有 widget 之后绘制，保证 z-order 正确）"""
        if not self._opened:
            return
        item_h = self._font.get_height() + 6
        max_visible = self._get_max_visible()
        list_h = max_visible * item_h + 4
        list_rect = pygame.Rect(self.rect.x, self.rect.bottom + 2, self.rect.width, list_h)

        pygame.draw.rect(screen, C_DROPDOWN_BG, list_rect, border_radius=4)
        pygame.draw.rect(screen, C_INPUT_BORDER, list_rect, width=1, border_radius=4)

        screen.set_clip(list_rect)
        for i in range(self._scroll_offset, min(self._scroll_offset + max_visible, len(self.options))):
            opt = self.options[i]
            item_y = list_rect.y + 2 + (i - self._scroll_offset) * item_h
            item_rect = pygame.Rect(self.rect.x + 2, item_y, self.rect.width - 4, item_h)

            mouse_pos = pygame.mouse.get_pos()
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, C_DROPDOWN_HOVER, item_rect, border_radius=2)

            # 高亮匹配的文本
            actual_idx = self._all_options.index(opt) if opt in self._all_options else -1
            color = C_ACCENT if actual_idx == self.selected_index else C_TEXT
            txt = self._font.render(opt, True, color)
            screen.blit(txt, (item_rect.x + 6, item_rect.y + 3))
        screen.set_clip(None)


class Button:
    """按钮"""
    def __init__(self, x: int, y: int, w: int, h: int, text: str, callback: Callable):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self._font = _get_font(16, bold=True)
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == MOUSEBUTTONDOWN:
            if self._hovered:
                self.callback()
                return True
        return False

    def update(self, dt: float):
        self._hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self, screen: pygame.Surface):
        color = C_BTN_HOVER if self._hovered else C_ACCENT
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        txt = self._font.render(self.text, True, C_WHITE)
        text_rect = txt.get_rect(center=self.rect.center)
        screen.blit(txt, text_rect)


class Label:
    """文本标签"""
    def __init__(self, x: int, y: int, text: str, size: int = 15):
        self.x = x
        self.y = y
        self.text = text
        self._font = _get_font(size)

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def update(self, dt: float):
        pass

    def draw(self, screen: pygame.Surface):
        txt = self._font.render(self.text, True, C_TEXT)
        screen.blit(txt, (self.x, self.y))


# ── 主 GUI ────────────────────────────────────────────

class RNGGui:
    def __init__(self):
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.init()
        self.W, self.H = 720, 470
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("EasyCon RNG 配置")

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "sprites", "shiny", "137.png")
        if os.path.exists(icon_path):
            icon_surf = pygame.image.load(icon_path).convert_alpha()
            min_x, min_y = icon_surf.get_width(), icon_surf.get_height()
            max_x, max_y = 0, 0
            w, h = icon_surf.get_size()
            pad = 4
            for y in range(0, h, pad):
                for x in range(0, w, pad):
                    if icon_surf.get_at((x, y)).a > 0:
                        min_x, min_y = min(min_x, x), min(min_y, y)
                        max_x, max_y = max(max_x, x), max(max_y, y)
            min_x = max(0, min_x - pad)
            min_y = max(0, min_y - pad)
            max_x = min(w - 1, max_x + pad)
            max_y = min(h - 1, max_y + pad)
            crop_w = max_x - min_x + 1
            crop_h = max_y - min_y + 1
            cropped = icon_surf.subsurface((min_x, min_y, crop_w, crop_h))
            icon_final = pygame.transform.smoothscale(cropped, (64, 64))
            pygame.display.set_icon(icon_final)

        pygame.key.set_repeat(400, 40)

        self.clock = pygame.time.Clock()
        self.running = True
        self._all_locations = _get_all_locations()
        self._result = None
        self._combo_widgets = []  # 单独存储 ComboBox，用于 overlay 绘制

        self._build_ui()
        self._load_and_apply_cache()

    def _load_and_apply_cache(self):
        """加载 rng_logs/latest.json 并填充到表单"""
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self._apply_cache(data)

    def _apply_cache(self, data: dict):
        """将缓存数据填充到控件"""
        # Game
        game = data.get("game", "")
        if game in self.game_combo._all_options:
            self.game_combo.selected_index = self.game_combo._all_options.index(game)

        # TID / SID
        self.tid_box.text = str(data.get("tid", "58888"))
        self.sid_box.text = str(data.get("sid", "12232"))

        # Settings
        self.settings_box.text = data.get("settings", DEFAULT_SETTINGS)

        # Method -> Category -> Location -> Pokemon 级联加载（不使用 on_change 回调以避免反复级联重置）
        method = data.get("method", "")
        if method in self.method_combo._all_options:
            self.method_combo.selected_index = self.method_combo._all_options.index(method)
        self.method_combo._filter_text = ""
        self.method_combo._apply_filter()
        # 手动填充 category 选项
        cats = METHOD_OPTIONS.get(method, {}).get("categories", [])
        self.category_combo.set_options(cats)

        category = data.get("category", "")
        if category in self.category_combo._all_options:
            self.category_combo.selected_index = self.category_combo._all_options.index(category)
        self.category_combo._filter_text = ""
        self.category_combo._apply_filter()
        # 手动填充 location 选项
        if method == "Wild" and category:
            locs = self._all_locations.get(category, [])
            self.location_combo.set_options(locs)
        else:
            self.location_combo.set_options([])

        location = data.get("location", "")
        if location in self.location_combo._all_options:
            self.location_combo.selected_index = self.location_combo._all_options.index(location)
        self.location_combo._filter_text = ""
        self.location_combo._apply_filter()
        # 手动刷新 pokemon
        self._refresh_pokemon_options()

        # Pokemon / Seed / Advances
        pokemon_name = str(data.get("pokemon", "Pikachu"))
        if pokemon_name in self.pokemon_combo._all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo._all_options.index(pokemon_name)
            self.pokemon_combo._filter_text = ""
            self.pokemon_combo._apply_filter()
        self.seed_box.text = str(data.get("seed", "B235"))
        self.advances_box.text = str(data.get("advances", "153142"))

    def _save_cache(self, data: dict):
        """保存当前参数到 rng_logs/latest.json"""
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    def _make_label(self, x, y, text, size=15):
        lbl = Label(x, y, text, size)
        self._widgets.append(lbl)
        return lbl

    def _make_textbox(self, x, y, w, h, placeholder=""):
        tb = TextBox(x, y, w, h, placeholder)
        self._widgets.append(tb)
        return tb

    def _make_button(self, x, y, w, h, text, callback):
        btn = Button(x, y, w, h, text, callback)
        self._widgets.append(btn)
        return btn

    def _make_searchable_combo(self, x, y, w, h, options=None, placeholder=""):
        cb = ComboBox(x, y, w, h, options, screen_height=self.H, placeholder=placeholder)
        self._widgets.append(cb)
        self._combo_widgets.append(cb)
        return cb

    def _build_ui(self):
        self._widgets = []
        PAD = 20
        ROW_H = 34
        ROW_GAP = 14
        BOX_W = 150  # 统一输入框宽度
        LABEL_BOX_GAP = 4  # label 和 box 之间的间距

        y0 = 20

        # ── 第一行：Game | TID | SID ──
        y1 = y0
        labels1 = [("Game:", 50), ("TID:", 32), ("SID:", 32)]
        # 每列宽度 = label_w + gap + BOX_W
        cols1 = [lw + LABEL_BOX_GAP + BOX_W for _, lw in labels1]
        total1 = sum(cols1)
        gap1 = (self.W - 2 * PAD - total1) // 2
        x = PAD

        self._make_label(x, y1 + 8, labels1[0][0])
        self.game_combo = self._make_searchable_combo(
            x + labels1[0][1] + LABEL_BOX_GAP, y1, BOX_W, ROW_H - 2,
            list(GAME_OPTIONS.keys()), placeholder="火红")
        self.game_combo.selected_index = 0

        x += cols1[0] + gap1
        self._make_label(x, y1 + 8, labels1[1][0])
        self.tid_box = self._make_textbox(x + labels1[1][1] + LABEL_BOX_GAP, y1, BOX_W, ROW_H - 2, "58888")

        x += cols1[1] + gap1
        self._make_label(x, y1 + 8, labels1[2][0])
        self.sid_box = self._make_textbox(x + labels1[2][1] + LABEL_BOX_GAP, y1, BOX_W, ROW_H - 2, "12232")

        # ── 第二行：Settings ──
        y2 = y1 + ROW_H + ROW_GAP
        lbl_w = 65
        self._make_label(PAD, y2 + 8, "Settings:")
        self.settings_box = self._make_textbox(
            PAD + lbl_w, y2, self.W - 2 * PAD - lbl_w, ROW_H - 2, DEFAULT_SETTINGS)

        # ── 第三行：Method | Category | Location ──
        y3 = y2 + ROW_H + ROW_GAP
        labels3 = [("Method:", 55), ("Category:", 72), ("Location:", 65)]
        cols3 = [lw + LABEL_BOX_GAP + BOX_W for _, lw in labels3]
        total3 = sum(cols3)
        gap3 = (self.W - 2 * PAD - total3) // 2
        x = PAD

        self._make_label(x, y3 + 8, labels3[0][0])
        self.method_combo = self._make_searchable_combo(
            x + labels3[0][1] + LABEL_BOX_GAP, y3, BOX_W, ROW_H - 2,
            list(METHOD_OPTIONS.keys()), placeholder="Wild")
        self.method_combo.set_on_change(self._on_method_change)

        x += cols3[0] + gap3
        self._make_label(x, y3 + 8, labels3[1][0])
        self.category_combo = self._make_searchable_combo(
            x + labels3[1][1] + LABEL_BOX_GAP, y3, BOX_W, ROW_H - 2,
            placeholder="Grass")
        self.category_combo.set_on_change(self._on_category_change)

        x += cols3[1] + gap3
        self._make_label(x, y3 + 8, labels3[2][0])
        self.location_combo = self._make_searchable_combo(
            x + labels3[2][1] + LABEL_BOX_GAP, y3, BOX_W, ROW_H - 2,
            placeholder="搜索地点...")
        self.location_combo.set_on_change(self._on_location_change)

        # ── 第四行：Pokemon | Seed | Advances ──
        y4 = y3 + ROW_H + ROW_GAP
        labels4 = [("Pokemon:", 72), ("Seed:", 42), ("Advances:", 70)]
        cols4 = [lw + LABEL_BOX_GAP + BOX_W for _, lw in labels4]
        total4 = sum(cols4)
        gap4 = (self.W - 2 * PAD - total4) // 2
        x = PAD

        self._make_label(x, y4 + 8, labels4[0][0])
        self.pokemon_combo = self._make_searchable_combo(
            x + labels4[0][1] + LABEL_BOX_GAP, y4, BOX_W, ROW_H - 2,
            placeholder="搜索宝可梦...")

        x += cols4[0] + gap4
        self._make_label(x, y4 + 8, labels4[1][0])
        self.seed_box = self._make_textbox(
            x + labels4[1][1] + LABEL_BOX_GAP, y4, BOX_W, ROW_H - 2, "B235")

        x += cols4[1] + gap4
        self._make_label(x, y4 + 8, labels4[2][0])
        self.advances_box = self._make_textbox(
            x + labels4[2][1] + LABEL_BOX_GAP, y4, BOX_W, ROW_H - 2, "153142")

        # ── 第五行：URL ──
        y5 = y4 + ROW_H + ROW_GAP
        url_label_w = 165
        btn_w2 = 90
        self._make_label(PAD, y5 + 8, "URL (ten-lines calibration):")
        self.url_box = self._make_textbox(
            PAD + url_label_w, y5, self.W - 2 * PAD - url_label_w - btn_w2 - 10, ROW_H - 2,
            placeholder="https://lincoln-lm.github.io/ten-lines/?...")
        self._make_button(self.W - PAD - btn_w2, y5, btn_w2, ROW_H - 2, "智能识别", self._on_parse_url)

        # ── 按钮行 ──
        btn_y = y5 + ROW_H + ROW_GAP
        btn_w = 120
        btn_gap = 14
        total_btn_w = btn_w * 4 + btn_gap * 3
        btn_x = (self.W - total_btn_w) // 2

        self._make_button(btn_x, btn_y, btn_w, 38, "确定", self._on_confirm)
        self._make_button(btn_x + btn_w + btn_gap, btn_y, btn_w, 38, "默认", self._on_default)
        self._make_button(btn_x + (btn_w + btn_gap) * 2, btn_y, btn_w, 38, "重置", self._on_reset)
        self._make_button(btn_x + (btn_w + btn_gap) * 3, btn_y, btn_w, 38, "退出", self._on_quit)

        # 状态提示
        self._status_text = ""
        self._status_color = C_TEXT_DIM
        self._status_font = _get_font(13)

    def _get_pokemon_options(self, method: str, category: str, location: str) -> list:
        """获取当前 method/category/location 下实际可选的宝可梦列表"""
        if method == "Wild" and location and category:
            species_ids = get_encounter_species_list(location, category)
            return [get_species_name(s) for s in species_ids]
        return []

    def _cascade_reset(self, level: int):
        """级联重置：method=0, category=1, location=2
        从指定 level 开始，递归重置该级及所有后续为第一个可选值"""
        if level <= 1:
            # 重置 category 为第一个
            cats = self.category_combo._all_options
            if cats:
                self.category_combo.selected_index = 0
            else:
                self.category_combo.selected_index = -1
            self.category_combo._filter_text = ""
            self.category_combo._apply_filter()

        if level <= 2:
            # 重置 location 为第一个
            method = self.method_combo.get_value()
            cat = self.category_combo.get_value()
            if method == "Wild" and cat:
                locs = self._all_locations.get(cat, [])
                self.location_combo.set_options(locs, 0 if locs else -1)
            else:
                self.location_combo.set_options([])

        # 重置 pokemon 为第一个可选选项
        self._refresh_pokemon_options()

    def _refresh_pokemon_options(self):
        """根据当前 method/category/location 刷新 Pokemon 下拉选项"""
        method = self.method_combo.get_value()
        cat = self.category_combo.get_value()
        loc = self.location_combo.get_value()
        opts = self._get_pokemon_options(method, cat, loc)
        self.pokemon_combo.set_options(opts, 0 if opts else -1)

    def _on_method_change(self):
        method = self.method_combo.get_value()
        cats = METHOD_OPTIONS.get(method, {}).get("categories", [])
        self.category_combo.set_options(cats, 0 if cats else -1)
        self._cascade_reset(level=1)

    def _on_category_change(self):
        self._cascade_reset(level=2)

    def _on_location_change(self):
        self._refresh_pokemon_options()

    def _on_confirm(self):
        data = self._collect_inputs()
        if data is None:
            self._set_status("请填写所有必填字段。", C_RED)
            return

        errors = self._validate(data)
        if errors:
            self._set_status(errors[0], C_RED)
            # 弹窗显示所有错误
            self._show_message("配置校验失败", "\n\n".join(errors))
            return

        self._save_cache(data)
        self._result = data
        self.running = False

    def _on_reset(self):
        self.game_combo.selected_index = 0
        self.tid_box.clear()
        self.sid_box.clear()
        self.settings_box.clear()
        self.method_combo.clear()
        self.category_combo.clear()
        self.location_combo.clear()
        self.pokemon_combo.clear()
        self.seed_box.clear()
        self.advances_box.clear()
        self.url_box.clear()
        self._set_status("已重置", C_TEXT_DIM)

    def _on_quit(self):
        self._result = None
        self.running = False

    def _on_parse_url(self):
        """解析 ten-lines URL 并自动填充表单"""
        url = self.url_box.get_value()
        if not url:
            self._set_status("请先输入 URL", C_RED)
            return

        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            # parse_qs 返回 {key: [values]}, 取第一个
            p = {k: v[0] for k, v in params.items()}
        except Exception:
            self._set_status("URL 解析失败", C_RED)
            return

        errors = []

        # Game
        game_rev = {"fr_nx": "火红", "lg_nx": "叶绿"}
        game = game_rev.get(p.get("game", ""), "")
        if game in self.game_combo._all_options:
            self.game_combo.selected_index = self.game_combo._all_options.index(game)
        else:
            errors.append("未识别的 game 参数")

        # TID / SID
        try:
            tid = int(p.get("trainerID", ""))
            if 0 <= tid <= 65535:
                self.tid_box.text = str(tid)
            else:
                errors.append(f"TID 越界: {tid}")
        except ValueError:
            errors.append("trainerID 无效")

        try:
            sid = int(p.get("secretID", ""))
            if 0 <= sid <= 65535:
                self.sid_box.text = str(sid)
            else:
                errors.append(f"SID 越界: {sid}")
        except ValueError:
            errors.append("secretID 无效")

        # Seed
        seed = p.get("targetInitialSeed", "").upper()
        try:
            int(seed, 16)
            self.seed_box.text = seed
        except ValueError:
            errors.append("targetInitialSeed 无效")

        # Advances (average of min/max)
        try:
            adv_min = int(p.get("advancesMin", "0"))
            adv_max = int(p.get("advancesMax", "0"))
            advances = (adv_min + adv_max) // 2
            if advances < 0:
                errors.append("advances 计算为负数")
            else:
                self.advances_box.text = str(advances)
        except ValueError:
            errors.append("advancesMin/advancesMax 无效")

        # Settings
        sound_map = {"mono": "Mono", "stereo": "Stereo"}
        sound = sound_map.get(p.get("sound", "").lower(), "Mono")

        btn_mode_map = {"a": "L=A", "h": "Help", "r": "LR"}
        btn_mode = btn_mode_map.get(p.get("buttonMode", "").lower(), "L=A")

        seed_btn_map = {"a": "A", "start": "Start", "l": "L (L=A)"}
        seed_btn = seed_btn_map.get(p.get("button", "").lower(), "A")

        held_map = {
            "none": "None", "startup_select": "Startup Select", "startup_a": "Startup A",
            "blackout_r": "Blackout R", "blackout_a": "Blackout A",
            "blackout_l": "Blackout L", "blackout_al": "Blackout A+L",
        }
        held = held_map.get(p.get("heldButton", "").lower(), "None")

        settings = f"{sound} | {btn_mode} | Seed Button: {seed_btn} | Extra Button: {held}"
        self.settings_box.text = settings

        if errors:
            self._set_status("部分字段解析成功: " + "; ".join(errors), C_RED)
        else:
            self._set_status("URL 智能识别完成", C_GREEN)

    def _on_default(self):
        """填充所有字段的默认值"""
        self.game_combo.selected_index = 0

        self.tid_box.text = "58888"
        self.tid_box.focused = False

        self.sid_box.text = "12232"
        self.sid_box.focused = False

        self.settings_box.text = DEFAULT_SETTINGS
        self.settings_box.focused = False

        self.method_combo.selected_index = 1  # Wild
        self.method_combo._filter_text = ""
        self.method_combo._apply_filter()
        self._on_method_change()

        self.category_combo.selected_index = 0  # Grass
        self.category_combo._filter_text = ""
        self.category_combo._apply_filter()
        self._on_category_change()

        # 设置 Location 为 Viridian Forest
        if "Viridian Forest" in self.location_combo._all_options:
            self.location_combo.selected_index = self.location_combo._all_options.index("Viridian Forest")
            self.location_combo._filter_text = ""
            self.location_combo._apply_filter()

        # 刷新 Pokemon 列表并默认选择 Pikachu
        self._refresh_pokemon_options()
        if "Pikachu" in self.pokemon_combo._all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo._all_options.index("Pikachu")
            self.pokemon_combo._filter_text = ""
            self.pokemon_combo._apply_filter()

        self.seed_box.text = "B235"
        self.seed_box.focused = False

        self.advances_box.text = "153142"
        self.advances_box.focused = False

        self._set_status("已填充默认值", C_TEXT_DIM)

    def _set_status(self, text: str, color: tuple):
        self._status_text = text
        self._status_color = color

    def _show_message(self, title: str, message: str):
        """用 pygame 显示简单消息框"""
        font = _get_font(14)
        font_title = _get_font(18, bold=True)
        lines = message.split("\n")

        line_height = font.get_height() + 4
        content_h = max(60, len(lines) * line_height + 60)
        msg_h = min(content_h, self.H - 40)
        msg_w = min(600, self.W - 40)
        msg_rect = pygame.Rect((self.W - msg_w) // 2, (self.H - msg_h) // 2, msg_w, msg_h)

        text_area_h = max(20, msg_h - 80)
        scroll_offset = 0
        max_scroll = max(0, len(lines) * line_height - text_area_h)

        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == QUIT:
                    self._result = None
                    self.running = False
                    return
                if event.type == KEYDOWN:
                    if event.key in (K_ESCAPE, K_RETURN, K_SPACE):
                        waiting = False
                if event.type == MOUSEBUTTONDOWN:
                    waiting = False
                if event.type == MOUSEWHEEL:
                    scroll_offset = max(0, min(max_scroll, scroll_offset - event.y * 20))

            # 基底绘制（不含 flip）
            self.screen.fill(C_BG)
            panel_rect = pygame.Rect(10, 10, self.W - 20, self.H - 20)
            pygame.draw.rect(self.screen, C_PANEL, panel_rect, border_radius=8)
            for w in self._widgets:
                w.draw(self.screen)
            for cb in self._combo_widgets:
                cb.draw_overlay(self.screen)
            if self._status_text:
                st = self._status_font.render(self._status_text, True, self._status_color)
                self.screen.blit(st, (20, self.H - 28))
            tf = _get_font(11)
            t = tf.render("EasyCon RNG 配置", True, C_TEXT_DIM)
            self.screen.blit(t, (self.W - t.get_width() - 20, self.H - 28))

            # 半透明遮罩
            overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))

            # 消息框
            pygame.draw.rect(self.screen, C_PANEL, msg_rect, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, msg_rect, width=2, border_radius=8)

            title_surf = font_title.render(title, True, C_RED)
            self.screen.blit(title_surf, (msg_rect.x + 20, msg_rect.y + 15))

            # 裁剪区域
            clip_rect = pygame.Rect(msg_rect.x + 16, msg_rect.y + 45, msg_w - 32, text_area_h)
            self.screen.set_clip(clip_rect)
            for i, line in enumerate(lines):
                y = msg_rect.y + 45 + i * line_height - scroll_offset
                line_surf = font.render(line, True, C_TEXT)
                self.screen.blit(line_surf, (msg_rect.x + 20, y))
            self.screen.set_clip(None)

            hint = font.render("按任意键关闭", True, C_TEXT_DIM)
            self.screen.blit(hint, (msg_rect.centerx - hint.get_width() // 2, msg_rect.bottom - 30))

            pygame.display.flip()
            self.clock.tick(60)

    def _collect_inputs(self) -> Optional[dict]:
        data = {}

        data["game"] = self.game_combo.get_value()
        if not data["game"]:
            return None

        tid_str = self.tid_box.get_value()
        if not tid_str:
            return None
        try:
            data["tid"] = int(tid_str)
        except ValueError:
            return None

        sid_str = self.sid_box.get_value()
        if not sid_str:
            return None
        try:
            data["sid"] = int(sid_str)
        except ValueError:
            return None

        settings_str = self.settings_box.get_value()
        data["settings"] = settings_str if settings_str else DEFAULT_SETTINGS

        data["method"] = self.method_combo.get_value()
        if not data["method"]:
            return None

        data["category"] = self.category_combo.get_value()
        if not data["category"]:
            return None

        data["location"] = self.location_combo.get_value()
        if data["method"] == "Wild" and not data["location"]:
            return None

        data["pokemon"] = self.pokemon_combo.get_value()
        if not data["pokemon"]:
            return None

        seed_str = self.seed_box.get_value()
        if not seed_str:
            return None
        data["seed"] = seed_str.strip().upper()

        adv_str = self.advances_box.get_value()
        if not adv_str:
            return None
        try:
            data["advances"] = int(adv_str)
        except ValueError:
            return None

        return data

    def _validate(self, data: dict) -> list:
        errors = []

        if data["game"] not in GAME_OPTIONS:
            errors.append(f"无效的 Game: {data['game']}")
        if not (0 <= data["tid"] <= 65535):
            errors.append(f"TID 必须在 0-65535 之间")
        if not (0 <= data["sid"] <= 65535):
            errors.append(f"SID 必须在 0-65535 之间")
        if data["method"] not in METHOD_OPTIONS:
            errors.append(f"无效的 Method: {data['method']}")
        if data["category"] not in METHOD_OPTIONS.get(data["method"], {}).get("categories", []):
            errors.append(f"Category '{data['category']}' 不适用于 Method '{data['method']}'")

        try:
            game_settings = GameSettings.from_string(data["settings"])
        except Exception as e:
            errors.append(f"Settings 格式错误: {e}")
            game_settings = None

        try:
            seed_int = int(data["seed"], 16)
            if not (0 <= seed_int <= 0xFFFF):
                errors.append(f"Seed 必须在 0x0000-0xFFFF 之间")
        except ValueError:
            errors.append(f"Seed 必须是有效的十六进制数")
            seed_int = None

        if data["advances"] < 0:
            errors.append(f"Advances 不能为负数")

        species_id = None
        try:
            species_id = get_species_id(data["pokemon"])
        except ValueError:
            try:
                en_name = get_species_en_name(data["pokemon"])
                species_id = get_species_id(en_name)
                data["pokemon"] = en_name
            except Exception:
                pass
        if species_id is None:
            errors.append(f"未找到宝可梦: {data['pokemon']}")

        if data["method"] == "Wild" and species_id is not None and data["location"]:
            encounter_species = get_encounter_species_list(data["location"], data["category"])
            if encounter_species and species_id not in encounter_species:
                avail = ", ".join(get_species_name(s) for s in encounter_species[:10])
                errors.append(
                    f"宝可梦 '{data['pokemon']}' 不在遭遇列表中\n可用: {avail}"
                )

        if errors:
            return errors

        game_version = GAME_OPTIONS[data["game"]]
        rng_method = METHOD_OPTIONS[data["method"]]["rng_method"]
        location = data["location"] if data["method"] == "Wild" else data["category"]

        try:
            cfg = RNGConfig(
                game_version=game_version,
                trainer_id=data["tid"],
                secret_id=data["sid"],
                game_settings=game_settings,
                pokemon_species=data["pokemon"],
                rng_category=data["category"],
                rng_location=location,
                rng_method=rng_method,
                target=RNGSlot(seed_int, 0, data["advances"]),
                seed_bias=-4000,
                advances_bias=-10000,
            )
        except KeyError as e:
            errors.append(f"Seed {data['seed']} 不在种子表中")
            return errors
        except Exception as e:
            errors.append(f"创建 RNG 配置失败: {e}")
            return errors

        limits = _read_calibration_limits()
        s = cfg.schedule
        if s.seed_ms < limits["seed_ms_min"]:
            errors.append(f"Seed 时间过短 ({s.seed_ms}ms < {limits['seed_ms_min']}ms)")
        if s.seed_ms > limits["seed_ms_max"]:
            errors.append(f"Seed 时间过长 ({s.seed_ms}ms > {limits['seed_ms_max']}ms)")
        if s.advances_ms_tv > 0 and s.advances_ms_tv < limits["tv_ms_min"]:
            errors.append(f"TV 时间过短 ({s.advances_ms_tv}ms < {limits['tv_ms_min']}ms)")
        if s.advances_ms_normal < limits["normal_ms_min"]:
            errors.append(f"Normal 时间过短 ({s.advances_ms_normal}ms < {limits['normal_ms_min']}ms)")

        try:
            target_results = calibration_api(
                game=game_version, tid=data["tid"], sid=data["sid"],
                method=rng_method, category=data["category"], location=location,
                pokemon=data["pokemon"], seed=f"{seed_int:04X}", advances=data["advances"],
                settings=game_settings, seed_bias=0, advances_bias=0,
            )
            is_shiny = any(r.shiny not in ("", "None") for r in target_results)
            if not is_shiny:
                errors.append("目标不是闪光! 请确认 Seed/Advances 是否正确。")
        except Exception as e:
            errors.append(f"闪光校验失败: {e}")

        return errors

    def _draw_all(self):
        self.screen.fill(C_BG)

        # 面板背景
        panel_rect = pygame.Rect(10, 10, self.W - 20, self.H - 20)
        pygame.draw.rect(self.screen, C_PANEL, panel_rect, border_radius=8)

        for w in self._widgets:
            w.draw(self.screen)

        # 下拉列表 overlay 最后绘制，确保不被其他 widget 遮挡
        for cb in self._combo_widgets:
            cb.draw_overlay(self.screen)

        # 状态栏
        if self._status_text:
            st = self._status_font.render(self._status_text, True, self._status_color)
            self.screen.blit(st, (20, self.H - 28))

        # 标题
        title_font = _get_font(11)
        title = title_font.render("EasyCon RNG 配置", True, C_TEXT_DIM)
        self.screen.blit(title, (self.W - title.get_width() - 20, self.H - 28))

        pygame.display.flip()

    def run(self) -> Optional[dict]:
        while self.running:
            dt = self.clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == QUIT:
                    self._result = None
                    self.running = False
                    break
                for w in self._widgets:
                    if w.handle_event(event):
                        break

            for w in self._widgets:
                w.update(dt)

            self._draw_all()

        pygame.quit()
        return self._result


# ── 脚本生成与运行 ────────────────────────────────────

def _generate_script(data: dict):
    game_version = GAME_OPTIONS[data["game"]]
    rng_method = METHOD_OPTIONS[data["method"]]["rng_method"]
    location = data["location"] if data["method"] == "Wild" else data["category"]
    seed_hex = data["seed"].upper()

    script = f'''# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, RNGSlot, SessionState
from examples.rng import launch

cfg = RNGConfig(
    game_version="{game_version}",
    trainer_id={data['tid']},
    secret_id={data['sid']},
    game_settings=GameSettings.from_string(
        "{data['settings']}"
    ),
    pokemon_species="{data['pokemon']}",
    rng_category="{data['category']}",
    rng_location="{location}",
    rng_method="{rng_method}",
    target=RNGSlot(0x{seed_hex}, 0, {data['advances']}),
    seed_bias=-4000,
    advances_bias=-10000,
    normal_ms_min=10000,
)
state = SessionState()

if __name__ == "__main__":
    launch(cfg, state)
'''

    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "examples", "rng_custom.py")

    if os.path.exists(script_path):
        mtime = os.path.getmtime(script_path)
        ts = datetime.fromtimestamp(mtime).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(os.path.dirname(script_path), f"rng_{ts}.py")
        shutil.move(script_path, backup_path)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)


def _run_script():
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "examples", "rng_custom.py")
    python_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "Python312", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    subprocess.Popen([python_exe, "-u", script_path],
                     cwd=os.path.dirname(os.path.abspath(__file__)))


# ── 入口 ──────────────────────────────────────────────

def main():
    gui = RNGGui()
    data = gui.run()

    if data is None:
        print("用户取消。")
        return

    # 生成脚本
    try:
        _generate_script(data)
    except Exception as e:
        print(f"脚本生成失败: {e}")
        return

    # 运行脚本
    _run_script()


if __name__ == "__main__":
    main()