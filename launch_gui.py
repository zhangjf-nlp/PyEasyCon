# -*- coding: utf-8 -*-
"""
LaunchGUI —— pygame GUI 基类，提供公共组件和布局框架
参考 run_rng_gui.py 和 run_scan_gui.py 的实现模式
"""

import json
import os
import subprocess
import sys
import threading
import time
from typing import Optional, Callable, List, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from pygame.locals import *

# ── 公共颜色 ───────────────────────────────────────────────────────────────────
C_BG             = (45, 45, 48)
C_PANEL          = (55, 55, 58)
C_TEXT           = (220, 220, 220)
C_TEXT_DIM       = (120, 120, 120)
C_ACCENT         = (70, 130, 200)
C_WHITE          = (255, 255, 255)
C_RED            = (220, 80, 80)
C_GREEN          = (80, 180, 80)
C_INPUT_BG       = (40, 40, 44)
C_INPUT_BORDER   = (80, 80, 85)
C_INPUT_FOCUS    = (70, 130, 200)
C_BTN_HOVER      = (75, 140, 210)
C_DROPDOWN_BG    = (50, 50, 55)
C_DROPDOWN_HOVER = (70, 130, 200)
C_DISABLED_BG    = (35, 35, 38)
C_DISABLED_TEXT  = (80, 80, 80)

# ── 布局超参数 ─────────────────────────────────────────────────────────────────
ROW_H      = 32    # row height
ROW_GAP    = 12    # vertical gap between rows
SIDE_PAD   = 18    # horizontal gap between adjacent InputUnits
BOX_W      = 150   # default input box width
LBL_W      = 60    # default label width

# ── 字体 ───────────────────────────────────────────────────────────────────────
FONT_CACHE = {}
FONT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "NotoSansCJKsc-Regular.otf")


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in FONT_CACHE:
        FONT_CACHE[key] = pygame.font.Font(FONT_PATH, size)
    return FONT_CACHE[key]


# ── Widgets ────────────────────────────────────────────────────────────────────

class Label:
    """文本标签"""
    def __init__(self, x: int, y: int, w: int, h: int, text: str, size: int = 15):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.font = get_font(size)

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def update(self, dt: float):
        pass

    def draw(self, screen: pygame.Surface):
        txt = self.font.render(self.text, True, C_TEXT)
        screen.blit(txt, (self.rect.x, self.rect.centery - txt.get_height() // 2))


class TextBox:
    """单行文本输入框"""
    def __init__(self, x: int, y: int, w: int, h: int,
                 placeholder: str = "", disabled: bool = False):
        self.rect        = pygame.Rect(x, y, w, h)
        self.text        = ""
        self.placeholder = placeholder
        self.focused     = False
        self.disabled    = disabled
        self.cursor_pos  = 0
        self.sel_start   = self.sel_end = -1
        self.cursor_visible = True
        self.cursor_timer   = 0
        self.font       = get_font(15)
        self.scroll_x    = 0
        self.dragging    = False
        self.ctrl_pressed: set = set()

    def get_sel(self):
        if self.sel_start == -1 or self.sel_end == -1:
            return None, None
        return min(self.sel_start, self.sel_end), max(self.sel_start, self.sel_end)

    def has_sel(self):
        s, e = self.get_sel()
        return s is not None and s != e

    def clear_sel(self):
        self.sel_start = self.sel_end = -1

    def del_sel(self):
        s, e = self.get_sel()
        if s is not None and s < e:
            self.text = self.text[:s] + self.text[e:]
            self.cursor_pos = s
            self.clear_sel()

    def sel_text(self) -> str:
        s, e = self.get_sel()
        if s is not None and s < e:
            return self.text[s:e]
        return ""

    def clip_copy(self):
        text = self.sel_text()
        if text:
            try:
                subprocess.run("clip", input=text, text=True, shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

    def clip_paste(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            paste_text = result.stdout
            if paste_text:
                paste_text = paste_text.replace("\n", "").replace("\r", "")
                self.del_sel()
                self.text = self.text[:self.cursor_pos] + paste_text + self.text[self.cursor_pos:]
                self.cursor_pos += len(paste_text)
                self.ensure_visible()
        except Exception:
            pass

    def x_to_pos(self, text, tx):
        for i in range(len(text) + 1):
            if self.font.size(text[:i])[0] > tx:
                return max(i - 1, 0)
        return len(text)

    def ensure_visible(self):
        pad = 6
        iw  = self.rect.width - pad * 2
        cx  = self.font.size(self.text[:self.cursor_pos])[0]
        if cx < self.scroll_x:
            self.scroll_x = cx
        elif cx > self.scroll_x + iw:
            self.scroll_x = cx - iw
        self.scroll_x = max(0, self.scroll_x)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.disabled:
            return False
        if event.type == MOUSEBUTTONDOWN and event.button == 1:
            hit = self.rect.collidepoint(event.pos)
            if hit:
                self.focused    = True
                rel_x           = event.pos[0] - self.rect.x - 6 + self.scroll_x
                self.cursor_pos = self.x_to_pos(self.text, rel_x)
                self.clear_sel()
                self.sel_start = self.sel_end = self.cursor_pos
                self.dragging  = True
            else:
                self.focused   = False
                self.clear_sel()
                self.dragging  = False
            return hit
        if event.type == MOUSEBUTTONUP:
            self.dragging = False
            return self.focused
        if event.type == MOUSEMOTION and self.dragging:
            rel_x = event.pos[0] - self.rect.x - 6 + self.scroll_x
            self.cursor_pos = self.x_to_pos(self.text, rel_x)
            self.sel_end    = self.cursor_pos
            self.ensure_visible()
            return True
        if event.type == KEYUP:
            self.ctrl_pressed.clear()
            return False
        if event.type == KEYDOWN and self.focused:
            mods  = pygame.key.get_mods()
            ctrl  = mods & KMOD_CTRL
            shift = mods & KMOD_SHIFT

            if ctrl and event.key == K_a:
                if "a" not in self.ctrl_pressed:
                    self.ctrl_pressed.add("a")
                    self.sel_start, self.sel_end = 0, len(self.text)
                    self.cursor_pos = len(self.text)
                return True
            if ctrl and event.key == K_c:
                if "c" not in self.ctrl_pressed:
                    self.ctrl_pressed.add("c")
                    self.clip_copy()
                return True
            if ctrl and event.key == K_v:
                if "v" not in self.ctrl_pressed:
                    self.ctrl_pressed.add("v")
                    self.clip_paste()
                return True
            if ctrl and event.key == K_x:
                if "x" not in self.ctrl_pressed:
                    self.ctrl_pressed.add("x")
                    self.clip_copy()
                    self.del_sel()
                    self.ensure_visible()
                return True
            if event.key == K_HOME:
                if shift:
                    if self.sel_start == -1:
                        self.sel_start = self.cursor_pos
                    self.sel_end = 0
                else:
                    self.clear_sel()
                self.cursor_pos = 0
                self.scroll_x   = 0
                return True
            if event.key == K_END:
                if shift:
                    if self.sel_start == -1:
                        self.sel_start = self.cursor_pos
                    self.sel_end = len(self.text)
                else:
                    self.clear_sel()
                self.cursor_pos = len(self.text)
                self.ensure_visible()
                return True
            if event.key == K_LEFT:
                if shift:
                    if self.sel_start == -1:
                        self.sel_start = self.cursor_pos
                    if self.cursor_pos > 0:
                        self.cursor_pos -= 1
                    self.sel_end = self.cursor_pos
                else:
                    if self.has_sel():
                        self.cursor_pos = min(self.sel_start, self.sel_end)
                        self.clear_sel()
                    elif self.cursor_pos > 0:
                        self.cursor_pos -= 1
                self.ensure_visible()
                return True
            if event.key == K_RIGHT:
                if shift:
                    if self.sel_start == -1:
                        self.sel_start = self.cursor_pos
                    if self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                    self.sel_end = self.cursor_pos
                else:
                    if self.has_sel():
                        self.cursor_pos = max(self.sel_start, self.sel_end)
                        self.clear_sel()
                    elif self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                self.ensure_visible()
                return True
            if event.key == K_BACKSPACE:
                if self.has_sel():
                    self.del_sel()
                elif self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
                self.ensure_visible()
                return True
            if event.key == K_DELETE:
                if self.has_sel():
                    self.del_sel()
                elif self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
                self.ensure_visible()
                return True
            if event.key in (K_RETURN, K_TAB, K_ESCAPE):
                self.focused = False
                self.clear_sel()
                return True
            if event.unicode and event.unicode.isprintable() and not ctrl:
                self.del_sel()
                self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                self.cursor_pos += 1
                self.ensure_visible()
                return True
            return True
        return False

    def update(self, dt: float):
        if self.focused and not self.disabled:
            self.cursor_timer += dt
            if self.cursor_timer > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0
        else:
            self.cursor_visible = False

    def draw(self, screen: pygame.Surface):
        bg     = C_DISABLED_BG   if self.disabled else C_INPUT_BG
        border = C_INPUT_BORDER  if self.disabled else (C_INPUT_FOCUS if self.focused else C_INPUT_BORDER)
        pygame.draw.rect(screen, bg, self.rect, border_radius=4)
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=4)
        pad = 6
        screen.set_clip(pygame.Rect(self.rect.x+pad, self.rect.y+2,
                                    self.rect.width-pad*2, self.rect.height-4))
        tx = self.rect.x + pad - self.scroll_x

        if self.text:
            s, e = self.get_sel()
            if s is not None and s < e and self.focused and not self.disabled:
                pre_w = self.font.size(self.text[:s])[0]
                sel_w = self.font.size(self.text[s:e])[0]
                sel_rect = pygame.Rect(tx + pre_w, self.rect.y + 4,
                                       sel_w, self.rect.height - 8)
                pygame.draw.rect(screen, (70, 130, 220), sel_rect)
            color = C_DISABLED_TEXT if self.disabled else C_TEXT
            surf  = self.font.render(self.text, True, color)
            screen.blit(surf, (tx, self.rect.centery - surf.get_height()//2))
        else:
            show  = "" if self.focused else self.placeholder
            color = C_DISABLED_TEXT if self.disabled else (C_TEXT if self.focused else C_TEXT_DIM)
            surf  = self.font.render(show, True, color)
            screen.blit(surf, (tx, self.rect.centery - surf.get_height()//2))
        if self.focused and self.cursor_visible and not self.disabled:
            cx = tx + self.font.size(self.text[:self.cursor_pos])[0]
            pygame.draw.line(screen, C_TEXT, (cx, self.rect.y+5), (cx, self.rect.bottom-5), 2)
        screen.set_clip(None)

    def get_value(self) -> str:
        return self.text.strip()

    def clear(self):
        self.text = ""
        self.cursor_pos = 0
        self.scroll_x   = 0
        self.clear_sel()
        self.focused = False


class ComboBox:
    """可搜索下拉选择框"""
    def __init__(self, x: int, y: int, w: int, h: int,
                 options: List[str] = None,
                 screen_height: int = 600,
                 placeholder: str = ""):
        self.rect            = pygame.Rect(x, y, w, h)
        self.all_options_    = options or []
        self.options         = list(self.all_options_)
        self.filter_text_    = ""
        self.selected_index  = -1
        self.opened          = False
        self.scroll_offset   = 0
        self.highlight_idx   = 0
        self.font            = get_font(14)
        self.on_change: Optional[Callable] = None
        self.screen_height_  = screen_height
        self.placeholder     = placeholder
        self.editing         = False
        self.cursor_visible  = True
        self.cursor_timer    = 0

    @property
    def all_options(self) -> List[str]:
        return self.all_options_

    @property
    def filter_text(self) -> str:
        return self.filter_text_

    @filter_text.setter
    def filter_text(self, v: str):
        self.filter_text_ = v

    @property
    def screen_height(self) -> int:
        return self.screen_height_

    @screen_height.setter
    def screen_height(self, v: int):
        self.screen_height_ = v

    def set_options(self, options: List[str], default_index: int = -1):
        self.all_options_   = options or []
        self.filter_text_   = ""
        self.apply_filter()
        self.selected_index = default_index
        self.opened        = False
        self.scroll_offset = 0
        self.editing       = False

    def set_on_change(self, cb: Callable):
        self.on_change = cb

    def apply_filter(self):
        ft = self.filter_text_.lower()
        self.options = ([o for o in self.all_options_ if ft in o.lower()]
                        if ft else list(self.all_options_))
        self.highlight_idx = 0
        self.scroll_offset = 0

    def get_value(self) -> str:
        if 0 <= self.selected_index < len(self.all_options_):
            return self.all_options_[self.selected_index]
        if self.filter_text_.strip():
            return self.filter_text_.strip()
        return ""

    def clear(self):
        self.filter_text_   = ""
        self.selected_index = -1
        self.opened        = False
        self.editing       = False
        self.apply_filter()

    def get_max_visible(self) -> int:
        item_h    = self.font.get_height() + 6
        available = self.screen_height_ - self.rect.bottom - 6
        return max(1, min(8, len(self.options), available // item_h))

    def select_by_filtered_index(self, filtered_idx: int):
        opt = self.options[filtered_idx]
        try:
            self.selected_index = self.all_options_.index(opt)
        except ValueError:
            self.selected_index = -1
        self.filter_text_   = ""
        self.apply_filter()
        self.opened        = False
        self.editing       = False
        self.scroll_offset = 0
        if self.on_change:
            self.on_change()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if not self.opened:
                    self.opened      = True
                    self.editing     = True
                    self.filter_text_ = ""
                    self.apply_filter()
                    self.scroll_offset = 0
                    self.highlight_idx = 0
                else:
                    self.opened  = False
                    self.editing = False
                return True
            elif self.opened:
                item_h      = self.font.get_height() + 6
                max_visible = self.get_max_visible()
                for i, opt in enumerate(self.options):
                    item_y = self.rect.bottom + 2 + (i - self.scroll_offset) * item_h
                    if 0 <= i - self.scroll_offset < max_visible:
                        item_rect = pygame.Rect(self.rect.x, item_y, self.rect.width, item_h)
                        if item_rect.collidepoint(event.pos):
                            self.select_by_filtered_index(i)
                            return True
                self.opened  = False
                self.editing = False
                return True
        if event.type == MOUSEWHEEL and self.opened:
            item_h      = self.font.get_height() + 6
            max_visible = self.get_max_visible()
            list_rect   = pygame.Rect(self.rect.x, self.rect.bottom + 2,
                                      self.rect.width, max_visible * item_h + 4)
            total       = len(self.options)
            mouse_pos   = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_pos) or list_rect.collidepoint(mouse_pos):
                self.highlight_idx = max(0, min(total - 1, self.highlight_idx - event.y))
                if self.highlight_idx < self.scroll_offset:
                    self.scroll_offset = self.highlight_idx
                elif self.highlight_idx >= self.scroll_offset + max_visible:
                    self.scroll_offset = self.highlight_idx - max_visible + 1
                return True
        if event.type == KEYDOWN and self.opened:
            max_vis = self.get_max_visible()
            total   = len(self.options)
            if event.key == K_ESCAPE:
                self.opened  = False
                self.editing = False
                return True
            if event.key == K_RETURN:
                if self.options and 0 <= self.highlight_idx < total:
                    self.select_by_filtered_index(self.highlight_idx)
                self.opened  = False
                self.editing = False
                return True
            if event.key == K_DOWN:
                if total == 0:
                    return True
                self.highlight_idx = (self.highlight_idx + 1) % total
                if self.highlight_idx < self.scroll_offset:
                    self.scroll_offset = self.highlight_idx
                elif self.highlight_idx >= self.scroll_offset + max_vis:
                    self.scroll_offset = self.highlight_idx - max_vis + 1
                return True
            if event.key == K_UP:
                if total == 0:
                    return True
                self.highlight_idx = (self.highlight_idx - 1) % total
                if self.highlight_idx < self.scroll_offset:
                    self.scroll_offset = self.highlight_idx
                elif self.highlight_idx >= self.scroll_offset + max_vis:
                    self.scroll_offset = max(0, self.highlight_idx - max_vis + 1)
                return True
            if event.key == K_RIGHT:
                if total == 0:
                    return True
                self.highlight_idx = min(total - 1, self.highlight_idx + max_vis)
                self.scroll_offset = min(max(0, total - max_vis), self.scroll_offset + max_vis)
                return True
            if event.key == K_LEFT:
                if total == 0:
                    return True
                self.highlight_idx = max(0, self.highlight_idx - max_vis)
                self.scroll_offset = max(0, self.scroll_offset - max_vis)
                return True
            if event.key == K_BACKSPACE:
                self.filter_text_ = self.filter_text_[:-1]
                self.apply_filter()
                self.highlight_idx = 0
                self.scroll_offset = 0
                return True
        if event.type == pygame.TEXTINPUT and self.opened:
            self.filter_text_ += event.text
            self.apply_filter()
            self.highlight_idx = 0
            self.scroll_offset = 0
            return True
        return False

    def update(self, dt: float):
        if self.editing:
            self.cursor_timer += dt
            if self.cursor_timer > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0
        else:
            self.cursor_visible = False

    def display_text(self) -> str:
        if self.opened:
            return self.filter_text_
        if self.selected_index >= 0:
            return self.all_options_[self.selected_index]
        return ""

    def draw(self, screen: pygame.Surface):
        border_color = C_INPUT_FOCUS if self.opened else C_INPUT_BORDER
        pygame.draw.rect(screen, C_INPUT_BG, self.rect, border_radius=4)
        pygame.draw.rect(screen, border_color, self.rect, width=2, border_radius=4)

        display = self.display_text()
        if display:
            txt = self.font.render(display, True, C_TEXT)
        elif self.editing:
            txt = self.font.render("", True, C_TEXT)
        else:
            txt = self.font.render(self.placeholder, True, C_TEXT_DIM)

        text_rect = txt.get_rect(midleft=(self.rect.x + 8, self.rect.centery))
        screen.blit(txt, text_rect)

        if self.editing and self.cursor_visible:
            cursor_x = text_rect.right + 2
            pygame.draw.line(screen, C_TEXT, (cursor_x, self.rect.y + 6),
                             (cursor_x, self.rect.bottom - 6), 2)

        arrow = self.font.render("▼", True, C_TEXT_DIM)
        screen.blit(arrow, (self.rect.right - 22, self.rect.centery - arrow.get_height() // 2))

    def draw_overlay(self, screen: pygame.Surface):
        if not self.opened:
            return
        item_h = self.font.get_height() + 6
        max_visible = self.get_max_visible()
        list_h = max_visible * item_h + 4
        list_rect = pygame.Rect(self.rect.x, self.rect.bottom + 2, self.rect.width, list_h)

        pygame.draw.rect(screen, C_DROPDOWN_BG, list_rect, border_radius=4)
        pygame.draw.rect(screen, C_INPUT_BORDER, list_rect, width=1, border_radius=4)

        screen.set_clip(list_rect)
        for i in range(self.scroll_offset, min(self.scroll_offset + max_visible, len(self.options))):
            opt = self.options[i]
            item_y = list_rect.y + 2 + (i - self.scroll_offset) * item_h
            item_rect = pygame.Rect(self.rect.x + 2, item_y, self.rect.width - 4, item_h)

            mouse_pos = pygame.mouse.get_pos()
            hovered = item_rect.collidepoint(mouse_pos)
            key_hl = (i == self.highlight_idx)
            is_selected = (self.all_options_.index(opt) if opt in self.all_options_ else -1) == self.selected_index

            if hovered:
                pygame.draw.rect(screen, C_DROPDOWN_HOVER, item_rect, border_radius=2)
            elif key_hl:
                pygame.draw.rect(screen, C_BTN_HOVER, item_rect, border_radius=2)

            if is_selected:
                color = C_WHITE if (hovered or key_hl) else C_ACCENT
            else:
                color = C_WHITE if hovered else C_TEXT
            txt = self.font.render(opt, True, color)
            screen.blit(txt, (item_rect.x + 6, item_rect.y + 3))
        screen.set_clip(None)


class Button:
    """按钮"""
    def __init__(self, x: int, y: int, w: int, h: int, text: str, callback: Callable,
                 right_callback: Optional[Callable] = None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.right_callback = right_callback
        self.font = get_font(16, bold=True)
        self.hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == MOUSEBUTTONDOWN and self.hovered:
            if event.button == 1:
                self.callback()
                return True
            if event.button == 3 and self.right_callback:
                self.right_callback()
                return True
        return False

    def update(self, dt: float):
        self.hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self, screen: pygame.Surface):
        color = C_BTN_HOVER if self.hovered else C_ACCENT
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        txt = self.font.render(self.text, True, C_WHITE)
        text_rect = txt.get_rect(center=self.rect.center)
        screen.blit(txt, text_rect)


class InputUnit:
    """A label + input box pair with a scale multiplier.

    total_width = (BOX_W + SIDE_PAD + LBL_W) * scale - SIDE_PAD
    box_width   = total_width - label_width
    """
    def __init__(self, x: int, y: int, scale: int,
                 box: "TextBox | ComboBox",
                 label_text: str, label_w: int = LBL_W):
        self.scale = scale
        total_w = (BOX_W + SIDE_PAD + LBL_W) * scale - SIDE_PAD
        box_w   = total_w - label_w
        self.label = Label(x, y, label_w, ROW_H, label_text)
        box.rect   = pygame.Rect(x + label_w, y, box_w, ROW_H)
        self.box   = box

    @property
    def width(self) -> int:
        return (BOX_W + SIDE_PAD + LBL_W) * self.scale - SIDE_PAD

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.box.handle_event(event)

    def update(self, dt: float):
        self.label.update(dt)
        self.box.update(dt)

    def draw(self, screen: pygame.Surface):
        self.label.draw(screen)
        self.box.draw(screen)


# ── LaunchGUI 基类 ─────────────────────────────────────────────────────────────

class LaunchGUI:
    """
    pygame GUI 基类，子类只需：
    1. 定义 TOTAL_SCALE
    2. 实现 build_ui() 方法
    3. 可选覆盖 apply_cache() / save_cache() / collect_inputs()
    """
    TOTAL_SCALE: int = 3          # 子类覆盖
    WINDOW_TITLE: str = "EasyCon" # 子类覆盖

    def __init__(self):
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.init()

        # W = (BOX_W + SIDE_PAD + LBL_W) * TOTAL_SCALE + SIDE_PAD
        self.W = (BOX_W + SIDE_PAD + LBL_W) * self.TOTAL_SCALE + SIDE_PAD
        self.H = 300
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption(self.WINDOW_TITLE)

        # 设置窗口图标（与现有 GUI 一致）
        project_root = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(project_root, "assets", "sprites", "shiny", "137.png")
        if os.path.exists(icon_path):
            icon_surf = pygame.image.load(icon_path).convert_alpha()
            min_x, min_y = icon_surf.get_width(), icon_surf.get_height()
            max_x, max_y = 0, 0
            iw, ih = icon_surf.get_size()
            pad = 4
            for py_val in range(0, ih, pad):
                for px_val in range(0, iw, pad):
                    if icon_surf.get_at((px_val, py_val)).a > 0:
                        min_x, min_y = min(min_x, px_val), min(min_y, py_val)
                        max_x, max_y = max(max_x, px_val), max(max_y, py_val)
            min_x = max(0, min_x - pad)
            min_y = max(0, min_y - pad)
            max_x = min(iw - 1, max_x + pad)
            max_y = min(ih - 1, max_y + pad)
            crop_w = max_x - min_x + 1
            crop_h = max_y - min_y + 1
            cropped = icon_surf.subsurface((min_x, min_y, crop_w, crop_h))
            icon_final = pygame.transform.smoothscale(cropped, (64, 64))
            pygame.display.set_icon(icon_final)

        pygame.key.set_repeat(400, 40)
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(pygame.Rect(0, 0, self.W, self.H))
        except Exception:
            pass  # 旧版 pygame 不支持

        self.clock          = pygame.time.Clock()
        self.running        = True
        self.result         = None
        self.widgets: list  = []
        self.combo_widgets: list = []
        self.panel_bg      = False  # 子类可设为 True 以绘制面板背景

        self.build_ui()
        self.load_cache()

    @property
    def combowidgets(self) -> list:
        """兼容别名：RNGGui 使用 combowidgets（无下划线）"""
        return self.combo_widgets

    # ── 子类覆盖 ──────────────────────────────────────────────────────────────

    def build_ui(self):
        """子类实现：在窗口中构建所有 UI 元素"""
        raise NotImplementedError

    def collect_inputs(self) -> Optional[dict]:
        """子类实现：从 UI 收集用户输入，返回 dict 或 None"""
        return None

    def apply_cache(self, data: dict):
        """子类实现：将缓存数据填充到控件（默认空实现）"""
        pass

    def save_cache(self, data: dict):
        """子类实现：保存用户输入到缓存文件（默认空实现）"""
        pass

    def validate(self, data: dict) -> list:
        """子类实现：验证输入，返回错误列表（默认空列表）"""
        return []

    def set_status(self, text: str, color=None):
        """显示状态消息"""
        if color is None:
            color = C_TEXT_DIM
        self.status_text  = text
        self.status_color = color

    # ── 按钮回调（可覆盖） ────────────────────────────────────────────────────

    def on_confirm(self):
        data = self.collect_inputs()
        if data is None:
            self.set_status("请填写所有必填字段。", C_RED)
            return
        errors = self.validate(data)
        if errors:
            self.set_status(errors[0], C_RED)
            return
        self.save_cache(data)
        self.result = data
        self.running = False

    def on_reset(self):
        """子类可覆盖以重置特定控件"""
        for w in self.widgets:
            if hasattr(w.box, 'clear'):
                w.box.clear()
        self.set_status("已重置", C_TEXT_DIM)

    def on_quit(self):
        self.result = None
        self.running = False

    # ── 缓存（默认实现） ──────────────────────────────────────────────────────

    def cache_file(self) -> str:
        """子类覆盖：返回缓存文件路径"""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "rng_logs", f"{self.__class__.__name__}_latest.json")

    def load_cache(self):
        path = self.cache_file()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.apply_cache(data)
        except Exception:
            pass

    def save_cache_impl(self, data: dict):
        path = self.cache_file()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 布局辅助 ──────────────────────────────────────────────────────────────

    def make_label(self, x: int, y: int, w: int, h: int, text: str, size: int = 15) -> Label:
        lbl = Label(x, y, w, h, text, size)
        self.widgets.append(lbl)
        return lbl

    def make_textbox(self, x: int, y: int, w: int, h: int,
                     placeholder: str = "") -> TextBox:
        tb = TextBox(x, y, w, h, placeholder)
        self.widgets.append(tb)
        return tb

    def make_combobox(self, x: int, y: int, w: int, h: int,
                      options: List[str] = None,
                      placeholder: str = "",
                      on_change: Callable = None) -> ComboBox:
        cb = ComboBox(x, y, w, h, options, screen_height=self.H,
                      placeholder=placeholder)
        if on_change is not None:
            cb.on_change = on_change
        self.widgets.append(cb)
        self.combo_widgets.append(cb)
        return cb

    def make_button(self, x: int, y: int, w: int, h: int,
                    text: str, callback: Callable,
                    right_callback: Optional[Callable] = None) -> Button:
        btn = Button(x, y, w, h, text, callback, right_callback)
        self.widgets.append(btn)
        return btn

    def add_row(self, y: int, specs: List[Tuple[int, str, Any, dict]]) -> int:
        """
        添加一行 InputUnit。

        specs: [(scale, label_text, box, kwargs), ...]
        - scale: 宽度比例（1 表示一个标准单元宽度）
        - label_text: 标签文字
        - box: TextBox 或 ComboBox 实例
        - kwargs: 传递给 InputUnit 的额外参数（如 label_w）

        返回下一行的 y 坐标。
        """
        x = SIDE_PAD
        for scale, lbl_text, box, kw in specs:
            lw   = kw.get("label_w", LBL_W)
            unit = InputUnit(x, y, scale, box, lbl_text, label_w=lw)
            self.widgets.append(unit)
            if isinstance(box, ComboBox) and box not in self.combo_widgets:
                self.combo_widgets.append(box)
            x += (BOX_W + SIDE_PAD + LBL_W) * scale - SIDE_PAD + SIDE_PAD
        return y + ROW_H + ROW_GAP

    def add_button_row(self, y: int, buttons: List[Tuple[str, Callable]],
                       btn_w: int = 120, btn_gap: int = 14,
                       right_callbacks: Optional[dict] = None) -> int:
        """添加按钮行，返回下一行的 y 坐标。
        right_callbacks: {index: callback} 指定索引按钮的右键回调。"""
        total_w = btn_w * len(buttons) + btn_gap * (len(buttons) - 1)
        bx = (self.W - total_w) // 2
        rc = right_callbacks or {}
        for i, (text, callback) in enumerate(buttons):
            self.make_button(bx + i * (btn_w + btn_gap), y, btn_w, 38, text,
                             callback, rc.get(i))
        return y + 38 + SIDE_PAD

    # ── 主循环 ────────────────────────────────────────────────────────────────

    def run(self) -> Optional[dict]:
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self.result = None
                    self.running = False
                    break
                for w in self.widgets:
                    if w.handle_event(ev):
                        break
            for w in self.widgets:
                w.update(dt)
            self.draw_base()
            pygame.display.flip()
        pygame.quit()
        return self.result

    def draw_base(self):
        """绘制基础背景和状态栏，子类可覆盖以添加额外绘制"""
        self.screen.fill(C_BG)
        # 可选面板背景（run_rng_gui / run_scan_gui 需要）
        if self.panel_bg:
            pygame.draw.rect(self.screen, C_PANEL,
                             pygame.Rect(10, 10, self.W - 20, self.H - 20),
                             border_radius=8)
        for w in self.widgets:
            w.draw(self.screen)
        for cb in self.combo_widgets:
            cb.draw_overlay(self.screen)

        # 状态栏
        if hasattr(self, 'status_text') and self.status_text:
            font = get_font(13)
            surf = font.render(self.status_text, True,
                              getattr(self, 'status_color', C_TEXT_DIM))
            self.screen.blit(surf, (20, self.H - 28))

        # 标题
        title = get_font(11).render(
            f"PyEasyCon {self.__class__.__name__}", True, C_TEXT_DIM)
        self.screen.blit(title, (self.W - title.get_width() - 20, self.H - 28))

    # ── 便捷方法 ──────────────────────────────────────────────────────────────

    def final_height(self, y: int) -> int:
        """根据最后一行 y 坐标计算并应用最终窗口高度"""
        return y + SIDE_PAD + 30

    def resize_to_fit(self):
        """调整窗口大小以适应内容"""
        self.screen = pygame.display.set_mode((self.W, self.H))
        for cb in self.combo_widgets:
            cb.screen_height = self.H

    # ── 通用弹窗 ──────────────────────────────────────────────────────────────

    def show_progress(self, check_func, progress: dict,
                      steps: List[str] = None,
                      title: str = "正在检测"):
        """显示进度弹窗，后台运行 check_func，更新 progress['step']

        Args:
            check_func: 后台执行的检测函数
            progress: 共享状态 dict，check_func 会设置 progress['step'] 和 progress['failed_msg']
            steps: 步骤描述列表，默认 None 则使用空白列表
            title: 弹窗标题
        """
        if steps is None:
            steps = []
        t = threading.Thread(target=check_func, daemon=True)
        t.start()

        font = get_font(14)
        font_title = get_font(18, bold=True)
        msg_w = min(420, self.W - 40)
        msg_h = max(120, 50 + len(steps) * 26)
        msg_rect = pygame.Rect((self.W - msg_w) // 2, (self.H - msg_h) // 2, msg_w, msg_h)

        while t.is_alive():
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self.result = None
                    self.running = False
                    return
            self.draw_base()
            # 半透明遮罩 + 弹窗
            overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            pygame.draw.rect(self.screen, C_PANEL, msg_rect, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, msg_rect, width=2, border_radius=8)
            self.screen.blit(font_title.render(title, True, C_TEXT),
                             (msg_rect.x + 20, msg_rect.y + 18))
            cur_step = progress.get("step", 0)
            for i, s in enumerate(steps):
                color = C_WHITE if i + 1 == cur_step else C_TEXT_DIM
                marker = "  > " if i + 1 == cur_step else "    "
                self.screen.blit(font.render(marker + s, True, color),
                                 (msg_rect.x + 24, msg_rect.y + 50 + i * 26))
            pygame.display.flip()
            self.clock.tick(30)

    def show_parallel_progress(self, checks: List[Tuple[str, Callable]],
                                title: str = "正在检测"):
        """并行进度弹窗——所有检测项同时运行，完成后显示 ✓/✗。

        checks: [(名称, check_func), ...]
          check_func 签名为 func(results: list, idx: int)，
          需设置 results[idx] = (ok: bool, msg: str)
        返回: results 列表，每个元素为 (ok, msg) 或 None（被中断）
        """
        n = len(checks)
        results: list = [None] * n  # None=进行中, (True/False, msg)=已完成
        threads = []

        def worker(idx, func):
            try:
                func(results, idx)
            except Exception as e:
                if results[idx] is None:
                    results[idx] = (False, str(e))

        for i, (_, func) in enumerate(checks):
            t = threading.Thread(target=worker, args=(i, func), daemon=True)
            t.start()
            threads.append(t)

        font = get_font(15)
        font_title = get_font(18, bold=True)
        font_status = get_font(15, bold=True)
        msg_w = min(420, self.W - 40)
        msg_h = 70 + n * 34
        msg_rect = pygame.Rect((self.W - msg_w) // 2, (self.H - msg_h) // 2,
                                msg_w, msg_h)

        while any(t.is_alive() for t in threads):
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self.result = None
                    self.running = False
                    return results

            self.draw_base()
            overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            pygame.draw.rect(self.screen, C_PANEL, msg_rect, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, msg_rect, width=2, border_radius=8)
            self.screen.blit(font_title.render(title, True, C_TEXT),
                             (msg_rect.x + 20, msg_rect.y + 18))

            for i, (name, _) in enumerate(checks):
                y = msg_rect.y + 52 + i * 34
                if results[i] is None:
                    status = "…"
                    color = C_TEXT_DIM
                elif results[i][0]:
                    status = "✓"
                    color = C_GREEN
                else:
                    status = "✗"
                    color = C_RED
                txt = font.render(f"  {name}", True, C_TEXT)
                self.screen.blit(txt, (msg_rect.x + 24, y))
                st = font_status.render(status, True, color)
                self.screen.blit(st, (msg_rect.x + msg_w - 48, y))

            pygame.display.flip()
            self.clock.tick(30)

        # 再渲染一次确保最终状态（✓/✗）显示出来
        self.draw_base()
        overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, C_PANEL, msg_rect, border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT, msg_rect, width=2, border_radius=8)
        self.screen.blit(font_title.render(title, True, C_TEXT),
                         (msg_rect.x + 20, msg_rect.y + 18))
        for i, (name, _) in enumerate(checks):
            y = msg_rect.y + 52 + i * 34
            if results[i] is None:
                status, color = "…", C_TEXT_DIM
            elif results[i][0]:
                status, color = "✓", C_GREEN
            else:
                status, color = "✗", C_RED
            txt = font.render(f"  {name}", True, C_TEXT)
            self.screen.blit(txt, (msg_rect.x + 24, y))
            st = font_status.render(status, True, color)
            self.screen.blit(st, (msg_rect.x + msg_w - 48, y))
        pygame.display.flip()

        # 短暂停留让用户看到完整结果
        time.sleep(0.5)

        return results

    def show_message(self, title: str, message: str):
        """显示消息弹窗，支持鼠标滚轮和滚动条"""
        font_title = get_font(18, bold=True)
        font = get_font(14)
        lines = message.split("\n")
        lh = font.get_height() + 4
        mh = min(max(80, len(lines) * lh + 70), self.H - 40)
        mw = min(600, self.W - 40)
        msg_rect = pygame.Rect((self.W - mw) // 2, (self.H - mh) // 2, mw, mh)
        text_area_h = max(20, mh - 80)
        text_area_top = msg_rect.y + 45
        text_area_rect = pygame.Rect(msg_rect.x + 16, text_area_top, mw - 44, text_area_h)
        scroll = 0.0
        max_scroll = max(0, len(lines) * lh - text_area_h)

        # scrollbar geometry
        sb_w = 8
        sb_x = msg_rect.right - 20
        sb_rect = pygame.Rect(sb_x, text_area_top, sb_w, text_area_h)
        thumb_h = max(20, text_area_h * text_area_h / max(len(lines) * lh, 1))
        drag_scrollbar = False

        waiting = True
        while waiting:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            for ev in pygame.event.get():
                if ev.type == QUIT or ev.type == pygame.WINDOWCLOSE:
                    self.result = None
                    self.running = False
                    return
                if ev.type == KEYDOWN:
                    if ev.key == K_ESCAPE:
                        waiting = False
                    elif ev.key == K_DOWN and max_scroll > 0:
                        scroll = min(max_scroll, scroll + lh)
                    elif ev.key == K_UP and max_scroll > 0:
                        scroll = max(0, scroll - lh)
                if ev.type == MOUSEBUTTONDOWN:
                    if ev.button == 1:
                        if sb_rect.collidepoint(mouse_x, mouse_y):
                            drag_scrollbar = True
                        elif not msg_rect.collidepoint(mouse_x, mouse_y):
                            waiting = False
                    elif ev.button == 3 and msg_rect.collidepoint(mouse_x, mouse_y):
                        waiting = False
                if ev.type == MOUSEBUTTONUP:
                    drag_scrollbar = False
                if ev.type == MOUSEWHEEL:
                    scroll = max(0, min(max_scroll, scroll - ev.y * 20))

            if drag_scrollbar and max_scroll > 0:
                rel_y = mouse_y - sb_rect.y - thumb_h // 2
                scroll = max(0, min(max_scroll, rel_y / (sb_rect.h - thumb_h) * max_scroll))

            # draw
            self.draw_base()
            overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            pygame.draw.rect(self.screen, C_PANEL, msg_rect, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, msg_rect, width=2, border_radius=8)
            self.screen.blit(font_title.render(title, True, C_RED),
                             (msg_rect.x + 20, msg_rect.y + 15))

            # text area with clip
            self.screen.set_clip(text_area_rect)
            y_off = msg_rect.x + 20
            for i, line in enumerate(lines):
                line_y = text_area_top + i * lh - int(scroll)
                if line_y + lh >= text_area_top and line_y <= text_area_top + text_area_h:
                    self.screen.blit(font.render(line, True, C_TEXT), (y_off, line_y))
            self.screen.set_clip(None)

            # scrollbar
            if max_scroll > 0:
                pygame.draw.rect(self.screen, (60, 60, 60), sb_rect, border_radius=4)
                thumb_top = sb_rect.y + int(scroll / max_scroll * (sb_rect.h - thumb_h))
                thumb_rect = pygame.Rect(sb_x, thumb_top, sb_w, thumb_h)
                pygame.draw.rect(self.screen, (140, 140, 140), thumb_rect, border_radius=4)

            hint = font.render("ESC / 右键关闭", True, C_TEXT_DIM)
            self.screen.blit(hint, (msg_rect.centerx - hint.get_width() // 2, msg_rect.bottom - 30))
            pygame.display.flip()
            self.clock.tick(60)


# ── 公共工具函数 ─────────────────────────────────────────────────────────────

def connect_controller():
    """连接并返回 EasyConController 实例，失败返回 None"""
    from easycon.controller import EasyConController
    try:
        c = EasyConController()
        if c.list_ports() and c.connect(timeout=2.0):
            return c
        return None
    except Exception:
        return None
