"""
Video Module - 游戏画面显示模块
负责实时显示游戏画面和键盘控制
"""

import os
import pygame
import cv2
import threading
from typing import Optional, Tuple, Dict
from easycon import EasyConController, GamePadKey
from easycon.config import get


class VideoModule:
    """游戏画面显示模块"""
    
    # 按键映射
    KEY_MAP = {
        pygame.K_y: GamePadKey.A, pygame.K_u: GamePadKey.B,
        pygame.K_i: GamePadKey.X, pygame.K_h: GamePadKey.Y,
        pygame.K_g: GamePadKey.L, pygame.K_t: GamePadKey.R,
        pygame.K_f: GamePadKey.ZL, pygame.K_r: GamePadKey.ZR,
        pygame.K_k: GamePadKey.PLUS, pygame.K_j: GamePadKey.MINUS,
        pygame.K_z: GamePadKey.CAPTURE, pygame.K_c: GamePadKey.HOME,
        pygame.K_q: GamePadKey.LCLICK, pygame.K_e: GamePadKey.RCLICK,
        pygame.K_w: GamePadKey.TOP, pygame.K_s: GamePadKey.DOWN,
        pygame.K_a: GamePadKey.LEFT, pygame.K_d: GamePadKey.RIGHT,
    }
    
    def __init__(self, x: int, y: int, width: int = 640, height: int = 360):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        
        # 视频捕获
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[pygame.Surface] = None
        self.raw_frame: Optional = None  # 原始 numpy 帧（供 OCR 等使用）
        self._frame_lock = threading.Lock()
        self.flip_vertical = get("capture.flip_vertical", False)
        self.flip_horizontal = get("capture.flip_horizontal", False)
        
        # 控制器
        self.controller: Optional[EasyConController] = None
        self.controller_connected = False
        self.controller_status = "未连接"
        self.last_reconnect_time = 0
        
        # 状态
        self.pressed_keys: set = set()
        self.focused = True  # 默认获得焦点，可直接操控游戏
        self.last_unmapped_key = None  # 最后按下的未映射按键
        self.unmapped_key_timer = 0  # 未映射按键提示计时器
        
        # FPS计算
        self.fps = 0
        self.frame_count = 0
        self.fps_timer = pygame.time.get_ticks()
        
        # VL模型类型显示
        self.model_type = "未知"
        
        # 初始化
        self._init_video()
    
    def _init_video(self):
        """初始化视频捕获"""
        def init_worker():
            try:
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(0)
                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as e:
                print(f"视频初始化错误: {e}")
                self.cap = None
        
        threading.Thread(target=init_worker, daemon=True).start()
    
    def set_controller(self, controller: EasyConController):
        """设置控制器"""
        self.controller = controller
        self._update_connection_status()
    
    def _update_connection_status(self):
        """更新连接状态"""
        if self.controller and self.controller.is_connected:
            self.controller_connected = True
            self.controller_status = "已连接"
        else:
            self.controller_connected = False
            self.controller_status = "未连接"
    
    def _check_and_reconnect(self):
        """检查连接状态并尝试重连"""
        current_time = pygame.time.get_ticks()
        
        # 每3秒检查一次连接状态
        if current_time - self.last_reconnect_time < 3000:
            return
        
        self.last_reconnect_time = current_time
        
        # 检查当前连接状态
        self._update_connection_status()
        if self.controller_connected:
            return
        
        # 尝试重连
        self.controller_status = "连接中..."
        
        def reconnect_worker():
            try:
                import serial.tools.list_ports
                
                if self.controller is None:
                    self.controller = EasyConController()
                
                ports = list(serial.tools.list_ports.comports())
                
                for port in ports:
                    try:
                        if self.controller.connect(port.device, timeout=1.0):
                            self._update_connection_status()
                            return
                    except:
                        continue
                
                self._update_connection_status()
            except Exception as e:
                self._update_connection_status()
        
        threading.Thread(target=reconnect_worker, daemon=True).start()
    
    def update(self):
        """更新视频帧"""
        if self.cap and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if self.flip_vertical:
                        frame_rgb = cv2.flip(frame_rgb, 0)
                    if self.flip_horizontal:
                        frame_rgb = cv2.flip(frame_rgb, 1)
                    frame_resized = cv2.resize(frame_rgb, (self.width, self.height))
                    self.current_frame = pygame.image.frombuffer(
                        frame_resized.tobytes(),
                        (self.width, self.height),
                        "RGB"
                    )
                    with self._frame_lock:
                        self.raw_frame = frame

                    # 计算FPS
                    self.frame_count += 1
                    current_time = pygame.time.get_ticks()
                    if current_time - self.fps_timer >= 1000:  # 每秒更新一次
                        self.fps = self.frame_count
                        self.frame_count = 0
                        self.fps_timer = current_time
                        
                        # 更新模型类型显示
                        try:
                            from vision.ocr import get_current_model_type, OLLAMA_MODEL_NAME, SILICONFLOW_MODEL
                            model_type = get_current_model_type()
                            if model_type == "vllm":
                                self.model_type = "vLLM(本地)"
                            elif model_type == "ollama":
                                self.model_type = f"{OLLAMA_MODEL_NAME}(Ollama)"
                            elif model_type == "siliconflow":
                                self.model_type = f"{SILICONFLOW_MODEL.split('/')[-1]}(SiliconFlow)"
                            else:
                                self.model_type = "未知"
                        except Exception:
                            pass
            except Exception as e:
                pass

    def get_raw_frame(self):
        """获取原始采集卡帧（线程安全，供 OCR 使用）"""
        with self._frame_lock:
            if self.raw_frame is not None:
                return self.raw_frame.copy()
        return None
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        处理事件
        Returns: 是否处理了该事件
        """
        # 鼠标点击视频区域获得焦点
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                if self.x <= mx <= self.x + self.width and self.y <= my <= self.y + self.height:
                    self.focused = True
                    return True
                else:
                    self.focused = False
        
        # 只有获得焦点时才处理键盘事件
        if self.focused:
            if event.type == pygame.KEYDOWN:
                if event.key in self.KEY_MAP:
                    key = self.KEY_MAP[event.key]
                    self.pressed_keys.add(key)
                    
                    # 检查控制器连接状态
                    if self.controller and self.controller.is_connected:
                        try:
                            self.controller.press(key)
                        except:
                            self.controller_connected = False
                            self.controller_status = "未连接"
                    else:
                        # 未连接时尝试重连
                        self._check_and_reconnect()
                elif event.key != pygame.K_TAB:
                    # 未映射的按键：记录并显示提示（Tab除外，它用于切换叠加信息）
                    self.last_unmapped_key = pygame.key.name(event.key)
                    self.unmapped_key_timer = pygame.time.get_ticks()
                
                return True
            
            elif event.type == pygame.KEYUP:
                if event.key in self.KEY_MAP:
                    key = self.KEY_MAP[event.key]
                    self.pressed_keys.discard(key)
                    if self.controller and self.controller.is_connected:
                        try:
                            self.controller.release(key)
                        except:
                            pass
                return True
        
        return False
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        """绘制视频区域"""
        # 背景
        pygame.draw.rect(screen, (25, 25, 30), (self.x, self.y, self.width, self.height))
        
        # 视频帧
        if self.current_frame:
            screen.blit(self.current_frame, (self.x, self.y))
        else:
            # 等待画面
            text = font.render("等待视频...", True, (150, 150, 150))
            rect = text.get_rect(center=(self.x + self.width // 2, self.y + self.height // 2))
            screen.blit(text, rect)
        
        # 边框（获得焦点时显示绿色边框）
        border_color = (0, 200, 0) if self.focused else (100, 100, 100)
        pygame.draw.rect(screen, border_color, (self.x, self.y, self.width, self.height), 3 if self.focused else 2)
        
        # 按住Tab时显示叠加信息（连接状态、按键映射等），松开即隐藏
        show_overlay = pygame.key.get_pressed()[pygame.K_TAB]
        
        if show_overlay:
            # 标题
            title = font.render("游戏画面", True, (200, 200, 200))
            screen.blit(title, (self.x + 10, self.y + 10))
            
            # 连接状态（右上角）
            if self.controller_status == "已连接":
                status_color = (0, 200, 0)
            elif self.controller_status == "连接中...":
                status_color = (200, 200, 0)
            else:
                status_color = (200, 100, 100)
            
            status_text = font.render(f"[{self.controller_status}]", True, status_color)
            status_rect = status_text.get_rect()
            status_rect.topright = (self.x + self.width - 10, self.y + 10)
            screen.blit(status_text, status_rect)
            
            # 焦点提示
            if self.focused:
                focus_hint = font.render("[已激活 - 键盘控制开启]", True, (0, 200, 0))
                screen.blit(focus_hint, (self.x + 80, self.y + 10))
            
            # 按键提示（按手柄真实布局分行，每行4个）
            hint_base_y = self.y + self.height - 12
            hint_spacing = 18
            hint_color = (150, 150, 150)
            
            hints = [
                "G=L  T=R  F=ZL  R=ZR",          # 肩键（顶部）
                "W=上  S=下  A=左  D=右",         # 方向键（左侧）
                "Y=A  U=B  I=X  H=Y",             # 功能键（右侧）
                "K=+  J=-  Z=拍照  C=HOME",        # 系统键（中部）
                "Q=LC  E=RC",                      # 摇杆按下
            ]
            for i, hint_text in enumerate(hints):
                hint_surf = font.render(hint_text, True, hint_color)
                screen.blit(hint_surf, (self.x + 10, hint_base_y - hint_spacing * (len(hints) - i)))
            
            # FPS显示（右下角）
            fps_text = font.render(f"{self.fps} FPS", True, (100, 200, 100))
            fps_rect = fps_text.get_rect()
            fps_rect.bottomright = (self.x + self.width - 10, self.y + self.height - 10)
            screen.blit(fps_text, fps_rect)
            
            # VL模型类型显示（FPS上方）
            model_text = font.render(f"VL: {self.model_type}", True, (100, 150, 200))
            model_rect = model_text.get_rect()
            model_rect.bottomright = (self.x + self.width - 10, self.y + self.height - 25)
            screen.blit(model_text, model_rect)
            
            # === OCR ROI 框叠加 (1920×1080 坐标 → 缩放到显示区域) ===
            try:
                from vision.ocr import get_all_roi_boxes
                rois = get_all_roi_boxes()
                scale_x = self.width / 1920.0
                scale_y = self.height / 1080.0
                small_font = pygame.font.Font(os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "assets", "NotoSansCJKsc-Regular.otf"), 9)
                for box in rois:
                    rx, ry, rw, rh = box['roi']
                    sx = self.x + int(rx * scale_x)
                    sy = self.y + int(ry * scale_y)
                    sw = max(2, int(rw * scale_x))
                    sh = max(2, int(rh * scale_y))
                    color = box['color']
                    pygame.draw.rect(screen, color, (sx, sy, sw, sh), 1)
                    label_surf = small_font.render(box['label'], True, color)
                    screen.blit(label_surf, (sx + 2, sy - 12))
            except Exception:
                pass
        
        # 未映射按键提示（始终显示，触发了就可见2秒）
        if self.last_unmapped_key and pygame.time.get_ticks() - self.unmapped_key_timer < 2000:
            unmapped_text = font.render(f"未定义按键: [{self.last_unmapped_key}]", True, (255, 180, 50))
            unmapped_rect = unmapped_text.get_rect()
            unmapped_rect.bottomright = (self.x + self.width - 10, self.y + self.height - 10)
            screen.blit(unmapped_text, unmapped_rect)
    
    def get_rect(self) -> pygame.Rect:
        """获取区域矩形"""
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def release(self):
        """释放资源"""
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
