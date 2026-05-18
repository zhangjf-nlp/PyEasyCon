"""
Label Maker Module - 标签制作模块
独立的截图显示和标签制作功能
"""

import pygame
import cv2
import json
import base64
import time
import os
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class LabelData:
    """标签数据结构"""
    name: str
    img_base64: str
    range_x: int
    range_y: int
    range_width: int
    range_height: int
    target_x: int
    target_y: int
    target_width: int
    target_height: int


class LabelMaker:
    """标签制作模块 - 独立的截图和标签制作功能"""
    
    def __init__(self, x: int, y: int, width: int = 360, height: int = 430):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        
        # 截图显示区域（放在上方，不被按钮盖住）
        self.capture_display_x = x + 10
        self.capture_display_y = y + 40
        self.capture_display_width = width - 20
        self.capture_display_height = 180
        
        # 标签数据
        self.labels_dir = "assets/labels"
        import os
        os.makedirs(self.labels_dir, exist_ok=True)
        
        # 当前截图（独立存储，不影响游戏画面）
        self.current_capture: Optional[np.ndarray] = None
        self.capture_surface: Optional[pygame.Surface] = None
        
        # 选择状态 - 同时支持 Range 和 Target 两个框
        self.selection_start: Optional[Tuple[int, int]] = None
        self.range_rect: Optional[Tuple[int, int, int, int]] = None  # 绿色 - 搜索范围
        self.target_rect: Optional[Tuple[int, int, int, int]] = None  # 红色 - 目标区域
        self.mode = "range"  # "range" 或 "target"
        
        # 已保存的标签
        self.saved_labels: List[str] = []
        self._refresh_saved_labels()
        
        # 按钮（3行2列，靠左 ~40% 宽度）
        btn_y = y + 230
        btn_w = 64
        btn_h = 28
        gap_x = 8
        gap_y = 6
        col1_x = x + 10
        col2_x = col1_x + btn_w + gap_x
        self.btn_region_w = col2_x + btn_w - x
        self.buttons = {
            'capture': pygame.Rect(col1_x, btn_y, btn_w, btn_h),
            'clear':    pygame.Rect(col2_x, btn_y, btn_w, btn_h),
            'range':    pygame.Rect(col1_x, btn_y + btn_h + gap_y, btn_w, btn_h),
            'target':   pygame.Rect(col2_x, btn_y + btn_h + gap_y, btn_w, btn_h),
            'save':     pygame.Rect(col1_x, btn_y + (btn_h + gap_y) * 2, btn_w, btn_h),
            'load':     pygame.Rect(col2_x, btn_y + (btn_h + gap_y) * 2, btn_w, btn_h),
        }
        
        self.btn_bottom = self.buttons['save'].bottom

        # 识别目标显示区域（按钮右侧）
        self.target_panel_x = x + self.btn_region_w + 10
        self.target_panel_w = width - self.btn_region_w - 20

        self.target_thumb: Optional[pygame.Surface] = None
        self.target_thumb_name: str = ""
        self.target_match: float = 0
        self._last_match_update = 0.0

        self.popup_mode = None
        self.popup_input = ""
        self.popup_scroll = 0
        self._popup_msg = ""


    def _refresh_saved_labels(self):
        """刷新已保存的标签列表"""
        import os
        try:
            self.saved_labels = [f.replace(".IL", "") for f in os.listdir(self.labels_dir) if f.endswith(".IL")]
        except:
            self.saved_labels = []
    
    def capture_frame(self, frame: np.ndarray):
        """
        捕获一帧作为截图
        这会定格当前画面，但不会影响游戏画面的实时刷新
        """
        if frame is not None:
            self.current_capture = frame.copy()
            self._update_capture_surface()
            self.range_rect = None
            self.target_rect = None
            self.selection_start = None
            self.target_thumb = None
            self.target_thumb_name = ""
            self.target_match = 0
            self._last_match_update = 0
            return True
        return False
    
    def _update_capture_surface(self):
        """更新截图显示表面"""
        if self.current_capture is not None:
            # 缩放以适应显示区域
            frame_rgb = cv2.cvtColor(self.current_capture, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (self.capture_display_width, self.capture_display_height))
            self.capture_surface = pygame.image.frombuffer(
                frame_resized.tobytes(),
                (self.capture_display_width, self.capture_display_height),
                "RGB"
            )
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.popup_mode:
            return self._handle_popup_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                for btn_name, btn_rect in self.buttons.items():
                    if btn_rect.collidepoint(mx, my):
                        if btn_name == 'capture':
                            return 'capture'
                        elif btn_name == 'clear':
                            self._clear_all()
                            return True
                        elif btn_name == 'range':
                            self.mode = 'range'
                        elif btn_name == 'target':
                            self.mode = 'target'
                        elif btn_name == 'save':
                            self._open_save_popup()
                            return True
                        elif btn_name == 'load':
                            self._open_load_popup()
                            return True
                        return True

                if self._is_in_capture_display(mx, my) and self.current_capture is not None:
                    self.selection_start = self._screen_to_capture_coords(mx, my)
                    return True

        elif event.type == pygame.MOUSEMOTION:
            if event.buttons[0] and self.selection_start and self.current_capture is not None:
                mx, my = event.pos
                current = self._screen_to_capture_coords(mx, my)
                x1, y1 = self.selection_start
                x2, y2 = current
                temp_rect = (
                    min(x1, x2),
                    min(y1, y2),
                    abs(x2 - x1),
                    abs(y2 - y1)
                )
                if self.mode == "range":
                    self.range_rect = temp_rect
                else:
                    self.target_rect = temp_rect
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.selection_start = None
                return True

        return False

    def _clear_all(self):
        self.current_capture = None
        self.capture_surface = None
        self.range_rect = None
        self.target_rect = None
        self.selection_start = None
        self.target_thumb = None
        self.target_thumb_name = ""
        self.target_match = 0
        self.mode = "range"

    def _open_save_popup(self):
        if self.current_capture is None:
            self._popup_msg = "请先截图"
            self.popup_mode = "msg"
            return
        if self.target_rect is None:
            self._popup_msg = "请先选择目标区域(Target)"
            self.popup_mode = "msg"
            return
        self.popup_mode = "save"
        self.popup_input = ""

    def _open_load_popup(self):
        self._refresh_saved_labels()
        self.popup_mode = "load"
        self.popup_scroll = 0

    def _popup_rect(self):
        pw, ph = 280, 260
        px = self.x + (self.width - pw) // 2
        py = self.y + (self.height - ph) // 2
        return pygame.Rect(px, py, pw, ph)

    def _handle_popup_event(self, event: pygame.event.Event):
        if self.popup_mode == "msg":
            if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.KEYDOWN:
                self.popup_mode = None
            return True

        pr = self._popup_rect()

        if event.type == pygame.TEXTINPUT and self.popup_mode == "save":
            self.popup_input += event.text
            return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.popup_mode = None
                return True
            if self.popup_mode == "save":
                if event.key == pygame.K_BACKSPACE:
                    self.popup_input = self.popup_input[:-1]
                elif event.key == pygame.K_RETURN:
                    self._do_save_label()
                elif not event.unicode:
                    if pygame.K_a <= event.key <= pygame.K_z:
                        self.popup_input += chr(event.key)
                    elif pygame.K_0 <= event.key <= pygame.K_9:
                        self.popup_input += chr(event.key)
                    elif event.key in (pygame.K_SPACE, pygame.K_MINUS, pygame.K_PERIOD):
                        self.popup_input += chr(event.key)
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not pr.collidepoint(mx, my):
                self.popup_mode = None
                return True

            if self.popup_mode == "save":
                btn_ok = pygame.Rect(pr.x + 60, pr.y + 200, 70, 28)
                btn_cancel = pygame.Rect(pr.x + 150, pr.y + 200, 70, 28)
                if btn_ok.collidepoint(mx, my):
                    self._do_save_label()
                elif btn_cancel.collidepoint(mx, my):
                    self.popup_mode = None
                return True

            if self.popup_mode == "load":
                btn_cancel = pygame.Rect(pr.x + 105, pr.y + 220, 70, 28)
                if btn_cancel.collidepoint(mx, my):
                    self.popup_mode = None
                    return True

                list_y_start = pr.y + 40
                item_h = 22
                visible = (pr.height - 100) // item_h
                for i, label_name in enumerate(self.saved_labels[self.popup_scroll:self.popup_scroll + visible]):
                    item_rect = pygame.Rect(pr.x + 10, list_y_start + i * item_h, pr.width - 20, item_h)
                    if item_rect.collidepoint(mx, my):
                        result = self._load_label(label_name)
                        self.popup_mode = None
                        return result

        if event.type == pygame.MOUSEWHEEL and self.popup_mode == "load":
            self.popup_scroll -= event.y
            visible = (self._popup_rect().height - 100) // 22
            max_scroll = max(0, len(self.saved_labels) - visible)
            self.popup_scroll = max(0, min(self.popup_scroll, max_scroll))
            return True

        return True

    def _do_save_label(self):
        label_name = self.popup_input.strip()
        if not label_name:
            self._popup_msg = "标签名不能为空"
            self.popup_mode = "msg"
            return
        import os
        if os.path.exists(os.path.join(self.labels_dir, f"{label_name}.IL")):
            self._popup_msg = f"标签 '{label_name}' 已存在"
            self.popup_mode = "msg"
            return
        result = self._save_label_with_name(label_name)
        self._refresh_saved_labels()
        self.popup_mode = None
        if isinstance(result, str):
            self._popup_msg = result
            self.popup_mode = "msg"
    
    def _is_in_capture_display(self, mx: int, my: int) -> bool:
        """检查坐标是否在截图显示区域内"""
        return (self.capture_display_x <= mx <= self.capture_display_x + self.capture_display_width and
                self.capture_display_y <= my <= self.capture_display_y + self.capture_display_height)
    
    def _screen_to_capture_coords(self, mx: int, my: int) -> Tuple[int, int]:
        """将屏幕坐标转换为截图内的坐标"""
        x = mx - self.capture_display_x
        y = my - self.capture_display_y
        
        # 限制在显示区域内
        x = max(0, min(x, self.capture_display_width))
        y = max(0, min(y, self.capture_display_height))
        
        return (x, y)
    
    def _load_label(self, label_name: str):
        """加载标签 — 保持当前截图为上下文，叠加 Range/Target 框"""
        try:
            import os
            label_path = os.path.join(self.labels_dir, f"{label_name}.IL")

            if not os.path.exists(label_path):
                return f"标签 '{label_name}' 不存在"

            with open(label_path, 'r', encoding='utf-8') as f:
                label_data = json.load(f)

            if self.current_capture is None:
                return "请先截图作为上下文"

            ch, cw = self.current_capture.shape[:2]
            scale_x = self.capture_display_width / cw
            scale_y = self.capture_display_height / ch

            has_coords = 'RangeX' in label_data

            if has_coords:
                rx = label_data.get('RangeX', 0)
                ry = label_data.get('RangeY', 0)
                rw = label_data.get('RangeWidth', cw)
                rh = label_data.get('RangeHeight', ch)
                self.range_rect = (int(rx * scale_x), int(ry * scale_y),
                                   int(rw * scale_x), int(rh * scale_y))

                tx = label_data.get('TargetX', 0)
                ty = label_data.get('TargetY', 0)
                tw = label_data.get('TargetWidth', cw)
                th = label_data.get('TargetHeight', ch)
                self.target_rect = (int(tx * scale_x), int(ty * scale_y),
                                    int(tw * scale_x), int(th * scale_y))

                roi = self.current_capture[
                    max(0, ry):min(ch, ry + rh),
                    max(0, rx):min(cw, rx + rw)
                ]
            else:
                self.range_rect = None
                self.target_rect = None
                roi = self.current_capture

            if label_data.get('ImgBase64'):
                img_bytes = base64.b64decode(label_data['ImgBase64'])
                nparr = np.frombuffer(img_bytes, np.uint8)
                cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if cv_img is not None:
                    h, w = cv_img.shape[:2]
                    th = 50
                    tw = int(w * th / h)
                    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                    rgb_resized = cv2.resize(rgb, (tw, th))
                    self.target_thumb = pygame.image.frombuffer(rgb_resized.tobytes(), (tw, th), "RGB")
                    self.target_thumb_name = label_name

                    if roi is not None and roi.size > 0 and roi.shape[0] >= h and roi.shape[1] >= w:
                        result = cv2.matchTemplate(roi, cv_img, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(result)
                        self.target_match = max_val * 100
                    else:
                        self.target_match = 0
                else:
                    self.target_thumb = None
                    self.target_match = 0

            return f"已加载标签: {label_name}"

        except Exception as e:
            return f"加载标签失败: {e}"
    
    def _save_label_with_name(self, label_name: str):
        """保存标签（使用指定名称）"""
        if self.current_capture is None:
            return "请先截图"
        
        if self.target_rect is None:
            return "请先选择目标区域(Target)"
        
        try:
            import os
            
            # 将显示坐标转换为原始图像坐标
            scale_x = self.current_capture.shape[1] / self.capture_display_width
            scale_y = self.current_capture.shape[0] / self.capture_display_height
            
            # 处理 Range 区域
            if self.range_rect:
                rx, ry, rw, rh = self.range_rect
                rx = max(0, min(rx, self.capture_display_width))
                ry = max(0, min(ry, self.capture_display_height))
                rw = min(rw, self.capture_display_width - rx)
                rh = min(rh, self.capture_display_height - ry)
                
                range_orig_x = int(rx * scale_x)
                range_orig_y = int(ry * scale_y)
                range_orig_w = int(rw * scale_x)
                range_orig_h = int(rh * scale_y)
            else:
                # 默认使用整个画面作为 Range
                range_orig_x, range_orig_y = 0, 0
                range_orig_w = self.current_capture.shape[1]
                range_orig_h = self.current_capture.shape[0]
            
            # 处理 Target 区域
            tx, ty, tw, th = self.target_rect
            tx = max(0, min(tx, self.capture_display_width))
            ty = max(0, min(ty, self.capture_display_height))
            tw = min(tw, self.capture_display_width - tx)
            th = min(th, self.capture_display_height - ty)
            
            if tw <= 0 or th <= 0:
                return "目标区域无效"
            
            target_orig_x = int(tx * scale_x)
            target_orig_y = int(ty * scale_y)
            target_orig_w = int(tw * scale_x)
            target_orig_h = int(th * scale_y)
            
            # 裁剪目标图像
            target_img = self.current_capture[target_orig_y:target_orig_y+target_orig_h, 
                                             target_orig_x:target_orig_x+target_orig_w]
            
            # 编码为Base64
            _, buffer = cv2.imencode('.png', target_img)
            img_base64 = base64.b64encode(buffer).decode()
            
            # 创建标签数据
            label_data = {
                "name": label_name,
                "ImgBase64": img_base64,
                "RangeX": range_orig_x,
                "RangeY": range_orig_y,
                "RangeWidth": range_orig_w,
                "RangeHeight": range_orig_h,
                "TargetX": target_orig_x,
                "TargetY": target_orig_y,
                "TargetWidth": target_orig_w,
                "TargetHeight": target_orig_h,
            }
            
            # 保存
            label_path = os.path.join(self.labels_dir, f"{label_name}.IL")
            with open(label_path, 'w', encoding='utf-8') as f:
                json.dump(label_data, f, indent=2)
            
            return f"标签已保存: {label_name}"
            
        except Exception as e:
            return f"保存标签失败: {e}"
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        """绘制标签制作区域"""
        # 背景
        pygame.draw.rect(screen, (30, 30, 35), (self.x, self.y, self.width, self.height))
        
        # 标题
        title = font.render("标签制作", True, (200, 200, 200))
        screen.blit(title, (self.x + 10, self.y + 10))
        
        # 截图显示区域背景
        pygame.draw.rect(screen, (20, 20, 25), 
                        (self.capture_display_x, self.capture_display_y, 
                         self.capture_display_width, self.capture_display_height))
        
        # 截图内容
        if self.capture_surface:
            screen.blit(self.capture_surface, (self.capture_display_x, self.capture_display_y))
            
            # 绘制 Range 框（绿色）
            if self.range_rect:
                rx, ry, rw, rh = self.range_rect
                pygame.draw.rect(screen, (0, 255, 0),
                               (self.capture_display_x + rx, self.capture_display_y + ry, rw, rh), 2)
                # 绘制标签
                label = small_font.render("Range", True, (0, 255, 0))
                screen.blit(label, (self.capture_display_x + rx, self.capture_display_y + ry - 14))
            
            # 绘制 Target 框（红色）
            if self.target_rect:
                tx, ty, tw, th = self.target_rect
                pygame.draw.rect(screen, (255, 80, 80),
                               (self.capture_display_x + tx, self.capture_display_y + ty, tw, th), 2)
                # 绘制标签
                label = small_font.render("Target", True, (255, 80, 80))
                screen.blit(label, (self.capture_display_x + tx, self.capture_display_y + ty - 14))
            
            # 如果正在拖拽，绘制临时框
            if self.selection_start:
                # 获取当前鼠标位置计算临时矩形
                mx, my = pygame.mouse.get_pos()
                if self._is_in_capture_display(mx, my):
                    current = self._screen_to_capture_coords(mx, my)
                    x1, y1 = self.selection_start
                    x2, y2 = current
                    temp_rect = (
                        min(x1, x2),
                        min(y1, y2),
                        abs(x2 - x1),
                        abs(y2 - y1)
                    )
                    tx, ty, tw, th = temp_rect
                    color = (0, 255, 0) if self.mode == "range" else (255, 80, 80)
                    pygame.draw.rect(screen, color,
                                   (self.capture_display_x + tx, self.capture_display_y + ty, tw, th), 2)
        else:
            # 提示文字
            hint = small_font.render("点击'截图'按钮捕获画面", True, (100, 100, 100))
            rect = hint.get_rect(center=(self.capture_display_x + self.capture_display_width // 2,
                                        self.capture_display_y + self.capture_display_height // 2))
            screen.blit(hint, rect)
        
        # 截图显示区域边框
        pygame.draw.rect(screen, (80, 80, 80),
                        (self.capture_display_x, self.capture_display_y,
                         self.capture_display_width, self.capture_display_height), 1)
        
        # 按钮
        self._draw_button(screen, small_font, 'capture', "截图", (60, 80, 120))
        self._draw_button(screen, small_font, 'clear', "清空", (100, 60, 60))
        self._draw_button(screen, small_font, 'range', "范围",
                         (80, 120, 80) if self.mode == "range" else (60, 60, 60))
        self._draw_button(screen, small_font, 'target', "目标",
                         (120, 80, 80) if self.mode == "target" else (60, 60, 60))
        self._draw_button(screen, small_font, 'save', "保存", (80, 120, 80))
        self._draw_button(screen, small_font, 'load', "加载", (80, 80, 120))

        self._update_match()
        self._draw_target_panel(screen, small_font)

        if self.popup_mode:
            self._draw_popup(screen, small_font)

        pygame.draw.rect(screen, (100, 100, 100), (self.x, self.y, self.width, self.height), 2)

    def _draw_popup(self, screen, font):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (self.x, self.y))

        pr = self._popup_rect()
        pygame.draw.rect(screen, (45, 45, 50), pr, border_radius=6)
        pygame.draw.rect(screen, (100, 100, 110), pr, 2, border_radius=6)

        if self.popup_mode == "msg":
            msg = font.render(self._popup_msg, True, (220, 220, 220))
            msg_rect = msg.get_rect(center=(pr.centerx, pr.centery))
            screen.blit(msg, msg_rect)
            return

        if self.popup_mode == "save":
            title = font.render("保存标签", True, (220, 220, 220))
            screen.blit(title, (pr.x + 15, pr.y + 12))

            inp_rect = pygame.Rect(pr.x + 15, pr.y + 40, pr.width - 30, 28)
            pygame.draw.rect(screen, (30, 30, 35), inp_rect, border_radius=3)
            pygame.draw.rect(screen, (150, 150, 150), inp_rect, 2, border_radius=3)
            if self.popup_input:
                text = font.render(self.popup_input, True, (220, 220, 220))
                screen.blit(text, (inp_rect.x + 6, inp_rect.y + 5))
            else:
                hint = font.render("输入标签名", True, (100, 100, 100))
                screen.blit(hint, (inp_rect.x + 6, inp_rect.y + 5))

            btn_ok = pygame.Rect(pr.x + 60, pr.y + 200, 70, 28)
            btn_cancel = pygame.Rect(pr.x + 150, pr.y + 200, 70, 28)
            self._draw_popup_button(screen, font, btn_ok, "确定", (60, 100, 60))
            self._draw_popup_button(screen, font, btn_cancel, "取消", (100, 60, 60))

        if self.popup_mode == "load":
            title = font.render("加载标签", True, (220, 220, 220))
            screen.blit(title, (pr.x + 15, pr.y + 12))

            list_y = pr.y + 40
            item_h = 22
            visible = (pr.height - 100) // item_h
            list_height = visible * item_h
            pygame.draw.rect(screen, (30, 30, 35), (pr.x + 10, list_y, pr.width - 20, list_height), border_radius=3)

            for i, label_name in enumerate(self.saved_labels[self.popup_scroll:self.popup_scroll + visible]):
                y = list_y + i * item_h
                item_rect = pygame.Rect(pr.x + 10, y, pr.width - 20, item_h)
                mx, my = pygame.mouse.get_pos()
                if item_rect.collidepoint(mx, my):
                    pygame.draw.rect(screen, (60, 80, 120), item_rect, border_radius=2)
                text = font.render(label_name, True, (200, 200, 200))
                screen.blit(text, (pr.x + 16, y + 3))

            btn_cancel = pygame.Rect(pr.x + 105, pr.y + 220, 70, 28)
            self._draw_popup_button(screen, font, btn_cancel, "取消", (100, 60, 60))

    def _update_match(self):
        now = time.time()
        if now - self._last_match_update < 1.0:
            return
        self._last_match_update = now
        if self.target_thumb_name and self.current_capture is not None and self.target_rect is not None:
            self._recalc_match()

    def _recalc_match(self):
        try:
            label_path = os.path.join(self.labels_dir, f"{self.target_thumb_name}.IL")
            if not os.path.exists(label_path):
                return
            with open(label_path, 'r', encoding='utf-8') as f:
                label_data = json.load(f)
            img_bytes = base64.b64decode(label_data['ImgBase64'])
            nparr = np.frombuffer(img_bytes, np.uint8)
            template = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if template is None:
                return
            ch, cw = self.current_capture.shape[:2]
            h, w = template.shape[:2]
            if self.range_rect:
                rx, ry, rw, rh = self.range_rect
                scale_x = cw / self.capture_display_width
                scale_y = ch / self.capture_display_height
                rx_orig = int(rx * scale_x)
                ry_orig = int(ry * scale_y)
                rw_orig = int(rw * scale_x)
                rh_orig = int(rh * scale_y)
                roi = self.current_capture[
                    max(0, ry_orig):min(ch, ry_orig + rh_orig),
                    max(0, rx_orig):min(cw, rx_orig + rw_orig)
                ]
            else:
                roi = self.current_capture
            if roi is not None and roi.size > 0 and roi.shape[0] >= h and roi.shape[1] >= w:
                result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                self.target_match = max_val * 100
        except Exception:
            pass

    def _draw_target_panel(self, screen, font):
        tx = self.target_panel_x
        ty = self.y + 230
        tw = self.target_panel_w
        th = self.y + self.height - 10 - ty

        header = font.render("识别目标", True, (150, 150, 150))
        screen.blit(header, (tx, ty))

        if self.target_thumb:
            thumb_x = tx + (tw - self.target_thumb.get_width()) // 2
            thumb_y = ty + 20
            screen.blit(self.target_thumb, (thumb_x, thumb_y))

            name_surf = font.render(self.target_thumb_name, True, (200, 200, 200))
            name_rect = name_surf.get_rect(center=(tx + tw // 2, thumb_y + self.target_thumb.get_height() + 14))
            screen.blit(name_surf, name_rect)

            match_str = f"匹配: {self.target_match:.1f}%"
            match_color = (80, 200, 80) if self.target_match >= 80 else (200, 180, 60)
            match_surf = font.render(match_str, True, match_color)
            match_rect = match_surf.get_rect(center=(tx + tw // 2, name_rect.bottom + 14))
            screen.blit(match_surf, match_rect)
        else:
            hint = font.render("未加载", True, (100, 100, 100))
            hint_rect = hint.get_rect(center=(tx + tw // 2, ty + 30))
            screen.blit(hint, hint_rect)

    def _draw_popup_button(self, screen, font, rect, text, color):
        mx, my = pygame.mouse.get_pos()
        c = tuple(min(255, v + 30) for v in color) if rect.collidepoint(mx, my) else color
        pygame.draw.rect(screen, c, rect, border_radius=4)
        t = font.render(text, True, (220, 220, 220))
        tr = t.get_rect(center=rect.center)
        screen.blit(t, tr)
    
    def _draw_button(self, screen: pygame.Surface, font: pygame.font.Font, 
                     btn_name: str, text: str, color: Tuple[int, int, int]):
        """绘制按钮"""
        rect = self.buttons[btn_name]
        
        # 检查鼠标悬停
        if rect.collidepoint(pygame.mouse.get_pos()):
            color = tuple(min(255, c + 20) for c in color)
        
        pygame.draw.rect(screen, color, rect, border_radius=3)
        pygame.draw.rect(screen, (150, 150, 150), rect, 1, border_radius=3)
        
        text_surf = font.render(text, True, (220, 220, 220))
        text_rect = text_surf.get_rect(center=rect.center)
        screen.blit(text_surf, text_rect)
    
    def get_rect(self) -> pygame.Rect:
        """获取区域矩形"""
        return pygame.Rect(self.x, self.y, self.width, self.height)
