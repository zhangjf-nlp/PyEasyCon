# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from typing import Optional, Callable, Union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from pygame.locals import *

from rng.tenlines_utils import (
    get_encounter_species_list,
    get_species_id,
    get_species_name,
    get_species_en_name,
    get_species_zh_name,
    load_frlg_encounters,
)
from easycon.controller import EasyConController

# ── constants ──────────────────────────────────────────────────────────────────
GAME_OPTIONS = {"火红": "fr_nx", "叶绿": "lg_nx"}

STATIC_CATEGORIES = ["Gift", "Game Corner", "Stationary", "Legend", "Fossil", "Event"]
WILD_CATEGORIES   = ["Grass", "Surfing", "SuperRod", "GoodRod", "OldRod"]

STATIC_POKEMON_MAP = {
    "Fossil":      ["Omanyte", "Kabuto", "Aerodactyl"],
    "Gift":        ["Eevee", "Lapras"],
    "Game Corner": ["Abra", "Clefairy", "Scyther", "Pinsir", "Dratini", "Porygon"],
    "Stationary":  ["Snorlax", "Electrode", "Hypno"],
    "Legend":      ["Articuno", "Zapdos", "Moltres", "Mewtwo"],
    "Event":       ["Deoxys", "Lugia", "Ho-Oh"],
}

METHOD_OPTIONS = {
    "Static": {"categories": STATIC_CATEGORIES},
    "Wild":   {"categories": WILD_CATEGORIES},
}

METHOD_ZH_TO_EN   = {"固定": "Static", "野生": "Wild"}
METHOD_EN_TO_ZH   = {"Static": "固定", "Wild": "野生"}
CATEGORY_ZH_TO_EN = {
    "赠送": "Gift", "游戏城": "Game Corner", "定点": "Stationary",
    "传说": "Legend", "化石": "Fossil", "活动": "Event",
    "草丛": "Grass", "冲浪": "Surfing", "超级钓竿": "SuperRod",
    "好钓竿": "GoodRod", "破旧钓竿": "OldRod",
}
CATEGORY_EN_TO_ZH = {v: k for k, v in CATEGORY_ZH_TO_EN.items()}

STATIC_POKEMON_ZH = {
    "Omanyte": "菊石兽", "Kabuto": "化石盔", "Aerodactyl": "化石翼龙",
    "Eevee": "伊布", "Lapras": "拉普拉斯",
    "Abra": "凯西", "Clefairy": "皮皮", "Scyther": "飞天螳螂",
    "Pinsir": "凯罗斯", "Dratini": "迷你龙", "Porygon": "多边兽",
    "Snorlax": "卡比兽", "Electrode": "顽皮雷弹", "Hypno": "引梦貘人",
    "Articuno": "急冻鸟", "Zapdos": "闪电鸟", "Moltres": "火焰鸟", "Mewtwo": "超梦",
    "Deoxys": "代欧奇希斯", "Lugia": "洛奇亚", "Ho-Oh": "凤王",
}
STATIC_POKEMON_ZH_TO_EN = {v: k for k, v in STATIC_POKEMON_ZH.items()}

LOCATION_EN_TO_ZH = {
    "Route 1": "1号道路", "Route 2": "2号道路", "Route 3": "3号道路",
    "Route 4": "4号道路", "Route 5": "5号道路", "Route 6": "6号道路",
    "Route 7": "7号道路", "Route 8": "8号道路", "Route 9": "9号道路",
    "Route 10": "10号道路", "Route 11": "11号道路", "Route 12": "12号道路",
    "Route 13": "13号道路", "Route 14": "14号道路", "Route 15": "15号道路",
    "Route 16": "16号道路", "Route 17": "17号道路", "Route 18": "18号道路",
    "Route 19": "19号道路", "Route 20": "20号道路",
    "Route 21": "21号道路", "Route 22": "22号道路", "Route 23": "23号道路",
    "Route 24": "24号道路", "Route 25": "25号道路",
    "Viridian Forest": "常青森林",
    "Mt Moon 1F": "月见山1F", "Mt Moon B1F": "月见山B1F", "Mt Moon B2F": "月见山B2F",
    "S.S Anne Exterior": "圣特安努号", "Digletts Cave B1F": "地鼠洞穴B1F",
    "Victory Road 1F/3F": "冠军之路1F/3F", "Victory Road 2F": "冠军之路2F",
    "Pokemon Mansion 1F-3F": "宝可梦屋1F-3F", "Pokemon Mansion B1F": "宝可梦屋B1F",
    "Safari Zone Center": "狩猎地带（入口）", "Safari Zone East": "狩猎地带东区（第1区）",
    "Safari Zone North": "狩猎地带北区（第2区）", "Safari Zone West": "狩猎地带西区（第3区）",
    "Cerulean Cave 1F": "华蓝洞窟1F", "Cerulean Cave 2F": "华蓝洞窟2F",
    "Cerulean Cave B1F": "华蓝洞窟B1F",
    "Rock Tunnel 1F": "岩山隧道1F", "Rock Tunnel B1F": "岩山隧道B1F",
    "Seafoam Islands 1F": "双子岛1F", "Seafoam Islands B1F": "双子岛B1F",
    "Seafoam Islands B2F": "双子岛B2F", "Seafoam Islands B3F": "双子岛B3F",
    "Seafoam Islands B4F": "双子岛B4F",
    "Pokemon Tower 3F": "宝可梦塔3F", "Pokemon Tower 4F-5F": "宝可梦塔4F-5F",
    "Pokemon Tower 6F": "宝可梦塔6F", "Pokemon Tower 7F": "宝可梦塔7F",
    "Power Plant": "无人发电厂",
    "Mt Ember Exterior": "灯火山（底部）",
    "Mt Ember Summit Path 1F/3F": "灯火山（山腰洞窟）1F/3F",
    "Mt Ember Summit Path 2F": "灯火山（山腰洞窟）2F",
    "Mt Ember Ruby Path 1F": "灯火山（红宝石之路）1F",
    "Mt Ember Ruby Path B1F": "灯火山（红宝石之路）B1F",
    "Mt Ember Ruby Path B2F": "灯火山（红宝石之路）B2F",
    "Mt Ember Ruby Path B3F": "灯火山（红宝石之路）B3F",
    "Mt Ember Ruby Path B1F Stairs": "灯火山（红宝石之路）B1F楼梯",
    "Mt Ember Ruby Path B2F Stairs": "灯火山（红宝石之路）B2F楼梯",
    "Three Island Berry Forest": "树果森林",
    "Four Island Icefall Cave Entrance": "冻瀑洞窟",
    "Four Island Icefall Cave 1F/B1F": "冻瀑洞窟1F/B1F",
    "Four Island Icefall Cave Back": "冻瀑洞窟（最深处）",
    "Six Island Pattern Bush": "标志之林",
    "Five Island Lost Cave": "不归之穴",
    "Five Island Lost Cave Room 1": "不归之穴 房间1",
    "Five Island Lost Cave Room 2": "不归之穴 房间2",
    "Five Island Lost Cave Room 3": "不归之穴 房间3",
    "Five Island Lost Cave Room 4": "不归之穴 房间4",
    "Five Island Lost Cave Room 5": "不归之穴 房间5",
    "Five Island Lost Cave Room 6": "不归之穴 房间6",
    "Five Island Lost Cave Room 7": "不归之穴 房间7",
    "Five Island Lost Cave Room 8": "不归之穴 房间8",
    "Five Island Lost Cave Room 9": "不归之穴 房间9",
    "Five Island Lost Cave Room 10": "不归之穴 房间10",
    "Five Island Lost Cave Room 11": "不归之穴 房间11",
    "Five Island Lost Cave Room 12": "不归之穴 房间12",
    "Five Island Lost Cave Room 13": "不归之穴 房间13",
    "Five Island Lost Cave Room 14": "不归之穴 房间14",
    "Five Island Lost Cave Item Room": "不归之穴（有物品的房间）",
    "One Island Kindle Road": "热气之路", "One Island Treasure Beach": "宝物海滩",
    "Two Island Cape Brink": "边缘海岬", "Three Island Bond Bridge": "索桥",
    "Three Island Port": "第3岛码头", "Five Island Resort Gorgeous": "豪华度假区",
    "Five Island Water Labyrinth": "水之迷宫", "Five Island Meadow": "第5岛空地",
    "Five Island Memorial Pillar": "回忆之塔", "Six Island Outcast Island": "外岛",
    "Six Island Green Path": "绿之步道", "Six Island Water Path": "水之步道",
    "Six Island Ruin Valley": "遗迹山谷", "Seven Island Trainer Tower": "训练家塔",
    "Seven Island Sevault Canyon Entrance": "溪谷入口",
    "Seven Island Sevault Canyon": "七宝溪谷",
    "Seven Island Tanoby Ruins": "阿斯卡纳遗迹",
    "Pallet Town": "真新镇", "Viridian City": "常青市",
    "Cerulean City": "华蓝市", "Vermilion City": "枯叶市",
    "Celadon City": "玉虹市", "Fuchsia City": "浅红市",
    "Cinnabar Island": "红莲镇",
    "One Island": "第1岛", "Four Island": "第4岛", "Five Island": "第5岛",
    "Six Island Altering Cave": "变幻洞窟",
}
LOCATION_ZH_TO_EN = {v: k for k, v in LOCATION_EN_TO_ZH.items()}

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "rng_logs", "scan_latest.json")

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

_FONT_CACHE = {}
_FONT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "NotoSansCJKsc-Regular.otf")

def _get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pygame.font.Font(_FONT_PATH, size)
    return _FONT_CACHE[key]

def _get_all_locations() -> dict:
    cat_to_locs: dict = {}
    for gv in ("fr_nx", "lg_nx"):
        for (loc, cat) in load_frlg_encounters(gv).keys():
            cat_to_locs.setdefault(cat, set()).add(loc)
    return {cat: sorted(locs) for cat, locs in cat_to_locs.items()}

def _loc_zh(en: str) -> str:
    return LOCATION_EN_TO_ZH.get(en, en)

def _loc_en(zh: str) -> str:
    return LOCATION_ZH_TO_EN.get(zh, zh)


# ── widgets ────────────────────────────────────────────────────────────────────

class TextBox:
    def __init__(self, x, y, w, h, placeholder="", disabled=False):
        self.rect        = pygame.Rect(x, y, w, h)
        self.text        = ""
        self.placeholder = placeholder
        self.focused     = False
        self.disabled    = disabled
        self.cursor_pos  = 0
        self._sel_start  = self._sel_end = -1
        self._cursor_visible = True
        self._cursor_timer   = 0
        self._font       = _get_font(15)
        self._scroll_x   = 0
        self._dragging   = False
        self._ctrl_pressed: set = set()

    def _get_sel(self):
        if self._sel_start == -1 or self._sel_end == -1:
            return None, None
        return min(self._sel_start, self._sel_end), max(self._sel_start, self._sel_end)

    def _has_sel(self):
        s, e = self._get_sel()
        return s is not None and s != e

    def _clear_sel(self):
        self._sel_start = self._sel_end = -1

    def _del_sel(self):
        s, e = self._get_sel()
        if s is not None and s < e:
            self.text = self.text[:s] + self.text[e:]
            self.cursor_pos = s
            self._clear_sel()

    def _x_to_pos(self, text, tx):
        for i in range(len(text) + 1):
            if self._font.size(text[:i])[0] > tx:
                return max(i - 1, 0)
        return len(text)

    def _ensure_visible(self):
        pad = 6
        iw  = self.rect.width - pad * 2
        cx  = self._font.size(self.text[:self.cursor_pos])[0]
        if cx < self._scroll_x:
            self._scroll_x = cx
        elif cx > self._scroll_x + iw:
            self._scroll_x = cx - iw
        self._scroll_x = max(0, self._scroll_x)

    def _sel_text(self) -> str:
        s, e = self._get_sel()
        if s is not None and s < e:
            return self.text[s:e]
        return ""

    def _clip_copy(self):
        text = self._sel_text()
        if text:
            try:
                subprocess.run("clip", input=text, text=True, shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

    def _clip_paste(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            paste_text = result.stdout
            if paste_text:
                paste_text = paste_text.replace("\n", "").replace("\r", "")
                self._del_sel()
                self.text = self.text[:self.cursor_pos] + paste_text + self.text[self.cursor_pos:]
                self.cursor_pos += len(paste_text)
                self._ensure_visible()
        except Exception:
            pass

    def handle_event(self, event):
        if self.disabled:
            return False
        if event.type == MOUSEBUTTONDOWN and event.button == 1:
            hit = self.rect.collidepoint(event.pos)
            if hit:
                self.focused   = True
                rel_x          = event.pos[0] - self.rect.x - 6 + self._scroll_x
                self.cursor_pos= self._x_to_pos(self.text, rel_x)
                self._clear_sel()
                self._sel_start = self._sel_end = self.cursor_pos
                self._dragging  = True
            else:
                self.focused   = False
                self._clear_sel()
                self._dragging = False
            return hit
        if event.type == MOUSEBUTTONUP:
            self._dragging = False
            return self.focused
        if event.type == MOUSEMOTION and self._dragging:
            rel_x = event.pos[0] - self.rect.x - 6 + self._scroll_x
            self.cursor_pos = self._x_to_pos(self.text, rel_x)
            self._sel_end   = self.cursor_pos
            self._ensure_visible()
            return True
        if event.type == KEYUP:
            self._ctrl_pressed.clear()
            return False
        if event.type == KEYDOWN and self.focused:
            mods  = pygame.key.get_mods()
            ctrl  = mods & KMOD_CTRL
            shift = mods & KMOD_SHIFT

            if ctrl and event.key == K_a:
                if "a" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("a")
                    self._sel_start, self._sel_end = 0, len(self.text)
                    self.cursor_pos = len(self.text)
                return True
            if ctrl and event.key == K_c:
                if "c" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("c")
                    self._clip_copy()
                return True
            if ctrl and event.key == K_v:
                if "v" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("v")
                    self._clip_paste()
                return True
            if ctrl and event.key == K_x:
                if "x" not in self._ctrl_pressed:
                    self._ctrl_pressed.add("x")
                    self._clip_copy()
                    self._del_sel()
                    self._ensure_visible()
                return True

            if event.key == K_HOME:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    self._sel_end = 0
                else:
                    self._clear_sel()
                self.cursor_pos = 0
                self._scroll_x   = 0
                return True
            if event.key == K_END:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    self._sel_end = len(self.text)
                else:
                    self._clear_sel()
                self.cursor_pos = len(self.text)
                self._ensure_visible()
                return True

            if event.key == K_LEFT:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    if self.cursor_pos > 0:
                        self.cursor_pos -= 1
                    self._sel_end = self.cursor_pos
                else:
                    if self._has_sel():
                        self.cursor_pos = min(self._sel_start, self._sel_end)
                        self._clear_sel()
                    elif self.cursor_pos > 0:
                        self.cursor_pos -= 1
                self._ensure_visible()
                return True
            if event.key == K_RIGHT:
                if shift:
                    if self._sel_start == -1:
                        self._sel_start = self.cursor_pos
                    if self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                    self._sel_end = self.cursor_pos
                else:
                    if self._has_sel():
                        self.cursor_pos = max(self._sel_start, self._sel_end)
                        self._clear_sel()
                    elif self.cursor_pos < len(self.text):
                        self.cursor_pos += 1
                self._ensure_visible()
                return True
            if event.key == K_BACKSPACE:
                if self._has_sel():
                    self._del_sel()
                elif self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
                self._ensure_visible()
                return True
            if event.key == K_DELETE:
                if self._has_sel():
                    self._del_sel()
                elif self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
                self._ensure_visible()
                return True
            if event.key in (K_RETURN, K_TAB, K_ESCAPE):
                self.focused = False
                self._clear_sel()
                return True
            if event.unicode and event.unicode.isprintable() and not ctrl:
                self._del_sel()
                self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                self.cursor_pos += 1
                self._ensure_visible()
                return True
            return True
        return False

    def update(self, dt):
        if self.focused and not self.disabled:
            self._cursor_timer += dt
            if self._cursor_timer > 0.5:
                self._cursor_visible = not self._cursor_visible
                self._cursor_timer = 0
        else:
            self._cursor_visible = False

    def draw(self, screen):
        bg     = C_DISABLED_BG   if self.disabled else C_INPUT_BG
        border = C_INPUT_BORDER  if self.disabled else (C_INPUT_FOCUS if self.focused else C_INPUT_BORDER)
        pygame.draw.rect(screen, bg, self.rect, border_radius=4)
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=4)
        pad = 6
        screen.set_clip(pygame.Rect(self.rect.x+pad, self.rect.y+2,
                                    self.rect.width-pad*2, self.rect.height-4))
        tx = self.rect.x + pad - self._scroll_x

        if self.text:
            s, e = self._get_sel()
            if s is not None and s < e and self.focused and not self.disabled:
                pre_w = self._font.size(self.text[:s])[0]
                sel_w = self._font.size(self.text[s:e])[0]
                sel_rect = pygame.Rect(tx + pre_w, self.rect.y + 4,
                                       sel_w, self.rect.height - 8)
                pygame.draw.rect(screen, (70, 130, 220), sel_rect)

            color = C_DISABLED_TEXT if self.disabled else C_TEXT
            surf  = self._font.render(self.text, True, color)
            screen.blit(surf, (tx, self.rect.centery - surf.get_height()//2))
        else:
            show  = "" if self.focused else self.placeholder
            color = C_DISABLED_TEXT if self.disabled else (C_TEXT if self.focused else C_TEXT_DIM)
            surf  = self._font.render(show, True, color)
            screen.blit(surf, (tx, self.rect.centery - surf.get_height()//2))
        if self.focused and self._cursor_visible and not self.disabled:
            cx = tx + self._font.size(self.text[:self.cursor_pos])[0]
            pygame.draw.line(screen, C_TEXT, (cx, self.rect.y+5), (cx, self.rect.bottom-5), 2)
        screen.set_clip(None)

    def get_value(self):
        return self.text.strip()

    def clear(self):
        self.text = ""
        self.cursor_pos = 0
        self._scroll_x  = 0
        self._clear_sel()
        self.focused = False


class ComboBox:
    """可搜索下拉选择框：支持文本输入 + 前缀匹配过滤 + 滚轮滚动 + 键盘上下左右键交互"""

    def __init__(self, x, y, w, h, options=None, screen_height=600, placeholder=""):
        self.rect            = pygame.Rect(x, y, w, h)
        self._all_options    = options or []
        self.options         = list(self._all_options)
        self._filter_text    = ""
        self.selected_index  = -1
        self._opened         = False
        self._scroll_offset  = 0
        self._highlight_idx  = 0
        self._font           = _get_font(14)
        self._on_change: Optional[Callable] = None
        self._screen_height  = screen_height
        self.placeholder     = placeholder
        self._editing        = False
        self._cursor_visible = True
        self._cursor_timer   = 0

    def set_options(self, options, default_index=-1):
        self._all_options   = options or []
        self._filter_text   = ""
        self._apply_filter()
        self.selected_index = default_index
        self._opened        = False
        self._scroll_offset = 0
        self._editing       = False

    def set_on_change(self, cb: Callable):
        self._on_change = cb

    def _apply_filter(self):
        ft = self._filter_text.lower()
        self.options = ([o for o in self._all_options if ft in o.lower()]
                        if ft else list(self._all_options))
        self._highlight_idx = 0
        self._scroll_offset = 0

    def get_value(self):
        if 0 <= self.selected_index < len(self._all_options):
            return self._all_options[self.selected_index]
        if self._filter_text.strip():
            return self._filter_text.strip()
        return ""

    def clear(self):
        self._filter_text   = ""
        self.selected_index = -1
        self._opened        = False
        self._editing       = False
        self._apply_filter()

    def _get_max_visible(self) -> int:
        item_h    = self._font.get_height() + 6
        available = self._screen_height - self.rect.bottom - 6
        return max(1, min(8, len(self.options), available // item_h))

    def _select_by_filtered_index(self, filtered_idx: int):
        """根据过滤列表中的索引，找到在 _all_options 中的实际索引并选中"""
        opt = self.options[filtered_idx]
        try:
            self.selected_index = self._all_options.index(opt)
        except ValueError:
            self.selected_index = -1
        self._filter_text   = ""
        self._apply_filter()
        self._opened        = False
        self._editing       = False
        self._scroll_offset = 0
        if self._on_change:
            self._on_change()

    def handle_event(self, event):
        if event.type == MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if not self._opened:
                    self._opened      = True
                    self._editing     = True
                    self._filter_text = ""
                    self._apply_filter()
                    self._scroll_offset = 0
                    self._highlight_idx = 0
                else:
                    self._opened  = False
                    self._editing = False
                return True
            elif self._opened:
                # 检查是否点击了下拉列表中的某项
                item_h      = self._font.get_height() + 6
                max_visible = self._get_max_visible()
                for i, opt in enumerate(self.options):
                    item_y = self.rect.bottom + 2 + (i - self._scroll_offset) * item_h
                    if 0 <= i - self._scroll_offset < max_visible:
                        item_rect = pygame.Rect(self.rect.x, item_y, self.rect.width, item_h)
                        if item_rect.collidepoint(event.pos):
                            self._select_by_filtered_index(i)
                            return True
                self._opened  = False
                self._editing = False
                return True
        if event.type == MOUSEWHEEL and self._opened:
            item_h      = self._font.get_height() + 6
            max_visible = self._get_max_visible()
            list_rect   = pygame.Rect(self.rect.x, self.rect.bottom + 2,
                                      self.rect.width, max_visible * item_h + 4)
            total       = len(self.options)
            mouse_pos   = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_pos) or list_rect.collidepoint(mouse_pos):
                self._highlight_idx = max(0, min(total - 1, self._highlight_idx - event.y))
                if self._highlight_idx < self._scroll_offset:
                    self._scroll_offset = self._highlight_idx
                elif self._highlight_idx >= self._scroll_offset + max_visible:
                    self._scroll_offset = self._highlight_idx - max_visible + 1
                return True
        if event.type == KEYDOWN and self._opened:
            max_vis = self._get_max_visible()
            total   = len(self.options)
            if event.key == K_ESCAPE:
                self._opened  = False
                self._editing = False
                return True
            if event.key == K_RETURN:
                if self.options and 0 <= self._highlight_idx < total:
                    self._select_by_filtered_index(self._highlight_idx)
                self._opened  = False
                self._editing = False
                return True
            if event.key == K_DOWN:
                if total == 0:
                    return True
                self._highlight_idx = (self._highlight_idx + 1) % total
                if self._highlight_idx < self._scroll_offset:
                    self._scroll_offset = self._highlight_idx
                elif self._highlight_idx >= self._scroll_offset + max_vis:
                    self._scroll_offset = self._highlight_idx - max_vis + 1
                return True
            if event.key == K_UP:
                if total == 0:
                    return True
                self._highlight_idx = (self._highlight_idx - 1) % total
                if self._highlight_idx < self._scroll_offset:
                    self._scroll_offset = self._highlight_idx
                elif self._highlight_idx >= self._scroll_offset + max_vis:
                    self._scroll_offset = max(0, self._highlight_idx - max_vis + 1)
                return True
            if event.key == K_RIGHT:
                # 向右：向下翻一页
                if total == 0:
                    return True
                self._highlight_idx = min(total - 1, self._highlight_idx + max_vis)
                self._scroll_offset = min(
                    max(0, total - max_vis),
                    self._scroll_offset + max_vis
                )
                return True
            if event.key == K_LEFT:
                # 向左：向上翻一页
                if total == 0:
                    return True
                self._highlight_idx = max(0, self._highlight_idx - max_vis)
                self._scroll_offset = max(0, self._scroll_offset - max_vis)
                return True
            if event.key == K_BACKSPACE:
                self._filter_text = self._filter_text[:-1]
                self._apply_filter()
                self._highlight_idx = 0
                self._scroll_offset = 0
                return True
        # TEXTINPUT 事件：正确处理所有文本输入（包括 IME 组合输入、中文等）
        if event.type == pygame.TEXTINPUT and self._opened:
            self._filter_text += event.text
            self._apply_filter()
            self._highlight_idx = 0
            self._scroll_offset = 0
            return True
        return False

    def update(self, dt):
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

    def draw(self, screen):
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

    def draw_overlay(self, screen):
        """绘制下拉列表（在所有 widget 之后绘制，保证 z-order 正确）"""
        if not self._opened:
            return
        item_h      = self._font.get_height() + 6
        max_visible = self._get_max_visible()
        list_h      = max_visible * item_h + 4
        list_rect   = pygame.Rect(self.rect.x, self.rect.bottom + 2, self.rect.width, list_h)

        # 确保不超出屏幕底部
        overflow = (list_rect.bottom + 4) - self._screen_height
        if overflow > 0:
            list_rect.h = max(item_h + 4, list_rect.h - overflow)

        pygame.draw.rect(screen, C_DROPDOWN_BG, list_rect, border_radius=4)
        pygame.draw.rect(screen, C_INPUT_BORDER, list_rect, width=1, border_radius=4)

        screen.set_clip(list_rect)
        for i in range(self._scroll_offset,
                       min(self._scroll_offset + max_visible, len(self.options))):
            opt       = self.options[i]
            item_y    = list_rect.y + 2 + (i - self._scroll_offset) * item_h
            item_rect = pygame.Rect(self.rect.x + 2, item_y, self.rect.width - 4, item_h)

            mouse_pos   = pygame.mouse.get_pos()
            hovered     = item_rect.collidepoint(mouse_pos)
            key_hl      = (i == self._highlight_idx)
            is_selected = ((self._all_options.index(opt)
                            if opt in self._all_options else -1)
                           == self.selected_index)

            if hovered:
                pygame.draw.rect(screen, C_DROPDOWN_HOVER, item_rect, border_radius=2)
            elif key_hl:
                pygame.draw.rect(screen, C_BTN_HOVER, item_rect, border_radius=2)

            # 选中项文字用白色在蓝色背景上，否则继承主题色
            if is_selected:
                color = C_WHITE if (hovered or key_hl) else C_ACCENT
            else:
                color = C_WHITE if hovered else C_TEXT
            txt = self._font.render(opt, True, color)
            screen.blit(txt, (item_rect.x + 6, item_rect.y + 3))
        screen.set_clip(None)


class Button:
    def __init__(self, x, y, w, h, text, callback):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self._font    = _get_font(16, bold=True)
        self._hovered = False

    def handle_event(self, event):
        if event.type == MOUSEBUTTONDOWN and event.button == 1 and self._hovered:
            self.callback()
            return True
        return False

    def update(self, dt):
        self._hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self, screen):
        pygame.draw.rect(screen, C_BTN_HOVER if self._hovered else C_ACCENT,
                         self.rect, border_radius=6)
        surf = self._font.render(self.text, True, C_WHITE)
        screen.blit(surf, surf.get_rect(center=self.rect.center))


class Label:
    def __init__(self, x, y, w, h, text, size=15):
        self.rect  = pygame.Rect(x, y, w, h)
        self.text  = text
        self._font = _get_font(size)

    def handle_event(self, event):
        return False

    def update(self, dt):
        pass

    def draw(self, screen):
        surf = self._font.render(self.text, True, C_TEXT)
        screen.blit(surf, (self.rect.x, self.rect.centery - surf.get_height()//2))


ROW_H    = 32
ROW_GAP  = 12
SIDE_PAD = 18
BOX_W    = 150
LBL_W    = 60


class InputUnit:
    def __init__(self, x, y, scale, box, label_text, label_w=LBL_W):
        self.scale = scale
        total_w    = (BOX_W + SIDE_PAD + LBL_W) * scale - SIDE_PAD
        box_w      = total_w - label_w
        self.label = Label(x, y, label_w, ROW_H, label_text)
        box.rect   = pygame.Rect(x + label_w, y, box_w, ROW_H)
        self.box   = box

    def handle_event(self, event):
        return self.box.handle_event(event)

    def update(self, dt):
        self.label.update(dt)
        self.box.update(dt)

    def draw(self, screen):
        self.label.draw(screen)
        self.box.draw(screen)


# ── main GUI ───────────────────────────────────────────────────────────────────

class ScanGui:
    def __init__(self):
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.init()
        TOTAL_SCALE = 2
        self.W = (BOX_W + SIDE_PAD + LBL_W) * TOTAL_SCALE + SIDE_PAD
        self.H = 400
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("EasyCon Scan 配置")
        pygame.key.set_repeat(400, 40)
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(pygame.Rect(0, 0, self.W, self.H))
        except Exception:
            pass
        self.clock          = pygame.time.Clock()
        self.running        = True
        self._all_locations = _get_all_locations()
        self._result        = None
        self._widgets:       list = []
        self._combo_widgets: list = []
        self._build_ui()
        self._load_cache()

    # ── cache ──────────────────────────────────────────────────────────────────

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_cache(data)
        except Exception:
            pass

    def _apply_cache(self, data):
        game = data.get("game", "")
        if game in self.game_combo._all_options:
            self.game_combo.selected_index = self.game_combo._all_options.index(game)

        method_en   = data.get("method", "")
        method_disp = METHOD_EN_TO_ZH.get(method_en, method_en)
        if method_disp in self.method_combo._all_options:
            self.method_combo.selected_index = self.method_combo._all_options.index(method_disp)
        self.method_combo._filter_text = ""
        self.method_combo._apply_filter()

        cats_en   = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        cats_disp = [CATEGORY_EN_TO_ZH.get(c, c) for c in cats_en]
        self.category_combo.set_options(cats_disp)
        cat_disp = CATEGORY_EN_TO_ZH.get(data.get("category", ""), "")
        if cat_disp in self.category_combo._all_options:
            self.category_combo.selected_index = self.category_combo._all_options.index(cat_disp)
        self.category_combo._filter_text = ""
        self.category_combo._apply_filter()

        self._reload_location_options(method_en, data.get("category", ""))
        loc_disp = _loc_zh(data.get("location", ""))
        if loc_disp in self.location_combo._all_options:
            self.location_combo.selected_index = self.location_combo._all_options.index(loc_disp)
        self.location_combo._filter_text = ""
        self.location_combo._apply_filter()

        self._refresh_pokemon_options()
        pkm_zh = get_species_zh_name(data.get("pokemon", ""))
        if pkm_zh and pkm_zh in self.pokemon_combo._all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo._all_options.index(pkm_zh)
            self.pokemon_combo._filter_text = ""
            self.pokemon_combo._apply_filter()

    def _save_cache(self, data):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        x0 = SIDE_PAD

        def _row(y, specs):
            x = x0
            for scale, lbl, box, kw in specs:
                lw   = kw.get("label_w", LBL_W)
                unit = InputUnit(x, y, scale, box, lbl, label_w=lw)
                self._widgets.append(unit)
                if isinstance(box, ComboBox):
                    self._combo_widgets.append(box)
                x += (BOX_W + SIDE_PAD + LBL_W) * scale - SIDE_PAD + SIDE_PAD

        y = SIDE_PAD

        # row 1: Method(1) | Category(1)
        method_opts = [METHOD_EN_TO_ZH.get(m, m) for m in METHOD_OPTIONS]
        method_cb   = ComboBox(0, 0, 0, ROW_H, method_opts,
                               screen_height=self.H, placeholder="野生")
        self.method_combo = method_cb

        cat_cb = ComboBox(0, 0, 0, ROW_H, [], screen_height=self.H, placeholder="草丛")
        self.category_combo = cat_cb

        _row(y, [
            (1, "方法:",   method_cb, {}),
            (1, "分类:",   cat_cb,   {}),
        ])
        self.method_combo.set_on_change(self._on_method_change)
        self.category_combo.set_on_change(self._on_category_change)

        # row 2: Location(2)
        y += ROW_H + ROW_GAP
        loc_cb = ComboBox(0, 0, 0, ROW_H, [], screen_height=self.H,
                          placeholder="刷闪地点")
        self.location_combo = loc_cb
        _row(y, [
            (2, "地点:",   loc_cb, {}),
        ])
        self.location_combo.set_on_change(self._on_location_change)

        # row 3: Game(1) | Pokemon(1)
        y += ROW_H + ROW_GAP
        game_cb = ComboBox(0, 0, 0, ROW_H, list(GAME_OPTIONS.keys()),
                           screen_height=self.H, placeholder="火红")
        game_cb.selected_index = 0
        self.game_combo = game_cb

        pkm_cb = ComboBox(0, 0, 0, ROW_H, [], screen_height=self.H,
                          placeholder="刷闪宝可梦")
        self.pokemon_combo = pkm_cb
        _row(y, [
            (1, "Game:",  game_cb,  {}),
            (1, "宝可梦:", pkm_cb, {}),
        ])

        # button row
        y += ROW_H + ROW_GAP
        btn_w, btn_gap = 120, 14
        bx = (self.W - (btn_w * 3 + btn_gap * 2)) // 2
        self._widgets.append(Button(bx,                      y, btn_w, 38, "确定", self._on_confirm))
        self._widgets.append(Button(bx + btn_w + btn_gap,    y, btn_w, 38, "重置", self._on_reset))
        self._widgets.append(Button(bx + (btn_w+btn_gap)*2,  y, btn_w, 38, "退出", self._on_quit))

        self.H = y + 38 + SIDE_PAD + 30
        self.screen = pygame.display.set_mode((self.W, self.H))
        for cb in self._combo_widgets:
            cb._screen_height = self.H

        self._status_text  = ""
        self._status_color = C_TEXT_DIM
        self._status_font  = _get_font(13)

    # ── cascade ────────────────────────────────────────────────────────────────

    def _get_method_en(self):
        return METHOD_ZH_TO_EN.get(self.method_combo.get_value(), self.method_combo.get_value())

    def _get_category_en(self):
        return CATEGORY_ZH_TO_EN.get(self.category_combo.get_value(), self.category_combo.get_value())

    def _get_location_en(self):
        return _loc_en(self.location_combo.get_value())

    def _reload_location_options(self, method_en, cat_en):
        if method_en == "Wild" and cat_en:
            locs = [_loc_zh(l) for l in self._all_locations.get(cat_en, [])]
            self.location_combo.set_options(locs, 0 if locs else -1)
        elif method_en == "Static" and cat_en:
            self.location_combo.set_options([CATEGORY_EN_TO_ZH.get(cat_en, cat_en)], 0)
        else:
            self.location_combo.set_options([])

    def _refresh_pokemon_options(self):
        method_en = self._get_method_en()
        cat_en    = self._get_category_en()
        loc_en    = self._get_location_en()
        game_ver  = GAME_OPTIONS.get(self.game_combo.get_value(), "fr_nx")
        if method_en == "Static" and cat_en:
            pkms = [STATIC_POKEMON_ZH.get(p, p) for p in STATIC_POKEMON_MAP.get(cat_en, [])]
        elif method_en == "Wild" and loc_en and cat_en:
            ids  = get_encounter_species_list(loc_en, cat_en, game_ver)
            pkms = [get_species_zh_name(s) for s in ids]
        else:
            pkms = []
        self.pokemon_combo.set_options(pkms, 0 if pkms else -1)

    def _on_method_change(self):
        method_en = self._get_method_en()
        cats_en   = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        self.category_combo.set_options(
            [CATEGORY_EN_TO_ZH.get(c, c) for c in cats_en], 0 if cats_en else -1)
        self._on_category_change()

    def _on_category_change(self):
        self._reload_location_options(self._get_method_en(), self._get_category_en())
        self._refresh_pokemon_options()

    def _on_location_change(self):
        self._refresh_pokemon_options()

    # ── buttons ────────────────────────────────────────────────────────────────

    def _set_status(self, text, color):
        self._status_text  = text
        self._status_color = color

    def _on_confirm(self):
        data = self._collect_inputs()
        if data is None:
            self._set_status("请填写所有必填字段。", C_RED)
            return

        progress = {"step": 0, "failed_msg": ""}

        def _checks():
            progress["step"] = 1
            errs = self._validate(data)
            if errs:
                progress["failed_msg"] = "\n\n".join(errs)
                return
            progress["step"] = 2
            try:
                c = EasyConController()
                if not c.list_ports() or not c.connect(timeout=2.0):
                    progress["failed_msg"] = "未识别到可用控制器"
                    return
                c.disconnect()
            except Exception:
                progress["failed_msg"] = "未识别到可用控制器"
                return
            progress["step"] = 3
            try:
                import cv2
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                ok = cap.isOpened()
                if ok:
                    cap.release()
                if not ok:
                    progress["failed_msg"] = "未识别到采集卡"
                    return
            except Exception:
                progress["failed_msg"] = "未识别到采集卡"

        self._show_progress(_checks, progress)

        if progress["failed_msg"]:
            self._show_message(
                "配置校验失败" if progress["step"] == 1 else "检测失败",
                progress["failed_msg"])
            self._set_status(progress["failed_msg"].split("\n")[0], C_RED)
            return

        self._save_cache(data)
        self._result = data
        self.running = False

    def _on_reset(self):
        self.game_combo.selected_index = 0
        self.method_combo.clear()
        self.category_combo.clear()
        self.location_combo.clear()
        self.pokemon_combo.clear()
        self._set_status("已重置", C_TEXT_DIM)

    def _on_quit(self):
        self._result = None
        self.running = False

    def _collect_inputs(self) -> Optional[dict]:
        data = {}
        data["game"] = self.game_combo.get_value()
        if not data["game"]:
            return None

        data["method"] = self._get_method_en()
        if not data["method"]:
            return None

        data["category"] = self._get_category_en()
        if not data["category"]:
            return None

        data["location"] = self._get_location_en()
        if data["method"] == "Wild" and not data["location"]:
            return None

        pkm_zh = self.pokemon_combo.get_value()
        if not pkm_zh:
            return None
        if data["method"] == "Static":
            data["pokemon"] = STATIC_POKEMON_ZH_TO_EN.get(pkm_zh, pkm_zh)
        else:
            data["pokemon"] = get_species_en_name(pkm_zh)
        if not data["pokemon"]:
            return None

        return data

    def _validate(self, data) -> list:
        errors = []
        if data["game"] not in GAME_OPTIONS:
            errors.append(f"无效的 Game: {data['game']}")
        if data["method"] not in METHOD_OPTIONS:
            errors.append(f"无效的 Method: {data['method']}")
        if data["category"] not in METHOD_OPTIONS.get(data["method"], {}).get("categories", []):
            errors.append(f"Category '{data['category']}' 不适用于 Method '{data['method']}'")

        species_id = None
        try:
            species_id = get_species_id(data["pokemon"])
        except Exception:
            errors.append(f"未找到宝可梦: {data['pokemon']}")

        game_ver = GAME_OPTIONS.get(data["game"], "fr_nx")

        if data["method"] == "Wild" and species_id is not None and data["location"]:
            enc = get_encounter_species_list(data["location"], data["category"], game_ver)
            if enc and species_id not in enc:
                avail = ", ".join(get_species_name(s) for s in enc[:10])
                errors.append(f"宝可梦 '{data['pokemon']}' 不在 {game_ver} 的遭遇列表中\n可用: {avail}")

        if data["method"] == "Static" and data["category"]:
            static_list = STATIC_POKEMON_MAP.get(data["category"], [])
            if static_list and data["pokemon"] not in static_list:
                errors.append(
                    f"宝可梦 '{data['pokemon']}' 不在 {data['category']} 遭遇列表中\n"
                    f"可用: {', '.join(static_list)}")

        return errors

    # ── progress / message dialogs ─────────────────────────────────────────────

    def _show_progress(self, check_func, progress):
        steps = ["(1/3) 正在验证参数...", "(2/3) 正在检测控制器...", "(3/3) 正在检测采集卡..."]
        t = threading.Thread(target=check_func, daemon=True)
        t.start()
        font_t = _get_font(18, bold=True)
        font   = _get_font(14)
        mw, mh = min(420, self.W-40), 150
        mr = pygame.Rect((self.W-mw)//2, (self.H-mh)//2, mw, mh)
        while t.is_alive():
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self._result = None; self.running = False; return
            self._draw_base()
            ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            self.screen.blit(ov, (0, 0))
            pygame.draw.rect(self.screen, C_PANEL, mr, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, mr, width=2, border_radius=8)
            self.screen.blit(font_t.render("正在检测", True, C_TEXT), (mr.x+20, mr.y+18))
            for i, s in enumerate(steps):
                color  = C_WHITE if i+1 == progress["step"] else C_TEXT_DIM
                marker = "  > " if i+1 == progress["step"] else "    "
                self.screen.blit(font.render(marker+s, True, color),
                                 (mr.x+24, mr.y+50+i*26))
            pygame.display.flip()
            self.clock.tick(30)

    def _show_message(self, title, message):
        font_t = _get_font(18, bold=True)
        font   = _get_font(14)
        lines  = message.split("\n")
        lh     = font.get_height() + 4
        mh = min(max(80, len(lines)*lh+70), self.H-40)
        mw = min(600, self.W-40)
        mr = pygame.Rect((self.W-mw)//2, (self.H-mh)//2, mw, mh)
        scroll = 0
        max_scroll = max(0, len(lines)*lh - (mh-80))
        waiting = True
        while waiting:
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self._result = None; self.running = False; return
                if ev.type in (KEYDOWN, MOUSEBUTTONDOWN):
                    waiting = False
                if ev.type == MOUSEWHEEL:
                    scroll = max(0, min(max_scroll, scroll - ev.y*20))
            self._draw_base()
            ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            self.screen.blit(ov, (0, 0))
            pygame.draw.rect(self.screen, C_PANEL, mr, border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT, mr, width=2, border_radius=8)
            self.screen.blit(font_t.render(title, True, C_RED), (mr.x+20, mr.y+15))
            clip = pygame.Rect(mr.x+16, mr.y+45, mw-32, mh-80)
            self.screen.set_clip(clip)
            for i, line in enumerate(lines):
                self.screen.blit(font.render(line, True, C_TEXT),
                                 (mr.x+20, mr.y+45+i*lh-scroll))
            self.screen.set_clip(None)
            hint = font.render("按任意键关闭", True, C_TEXT_DIM)
            self.screen.blit(hint, (mr.centerx-hint.get_width()//2, mr.bottom-30))
            pygame.display.flip()
            self.clock.tick(60)

    # ── draw ───────────────────────────────────────────────────────────────────

    def _draw_base(self):
        self.screen.fill(C_BG)
        pygame.draw.rect(self.screen, C_PANEL,
                         pygame.Rect(10, 10, self.W-20, self.H-20), border_radius=8)
        for w in self._widgets:
            w.draw(self.screen)
        for cb in self._combo_widgets:
            cb.draw_overlay(self.screen)
        if self._status_text:
            surf = self._status_font.render(self._status_text, True, self._status_color)
            self.screen.blit(surf, (20, self.H-28))
        title = _get_font(11).render("PyEasyCon Scan Configuration", True, C_TEXT_DIM)
        self.screen.blit(title, (self.W - title.get_width() - 20, self.H-28))

    def run(self) -> Optional[dict]:
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    self._result = None; self.running = False; break
                for w in self._widgets:
                    if w.handle_event(ev):
                        break
            for w in self._widgets:
                w.update(dt)
            self._draw_base()
            pygame.display.flip()
        pygame.quit()
        return self._result


# ── script generation ──────────────────────────────────────────────────────────

def _generate_script(data: dict):
    game_ver  = GAME_OPTIONS[data["game"]]
    method    = data["method"]
    category  = data["category"]
    location  = data["location"] if method == "Wild" else category
    pokemon   = data["pokemon"]

    script = f'''# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.scan import launch

if __name__ == "__main__":
    launch(
        method="{method}",
        category="{category}",
        location="{location}",
        pokemon_species="{pokemon}",
        game_version="{game_ver}",
    )
'''
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "examples", f"scan_custom_{ts}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    return script_path


def _run_script(script_path: str):
    python_exe  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "Python312", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    subprocess.Popen([python_exe, "-u", script_path],
                     cwd=os.path.dirname(os.path.abspath(__file__)))


# ── entry ──────────────────────────────────────────────────────────────────────

def main():
    gui  = ScanGui()
    data = gui.run()
    if data is None:
        print("用户取消。")
        return
    try:
        script_path = _generate_script(data)
    except Exception as e:
        print(f"脚本生成失败: {e}")
        return
    _run_script(script_path)


if __name__ == "__main__":
    main()

