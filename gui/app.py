"""
EasyCon GUI - 模块化版本
布局：
- 左上：游戏画面（VideoModule）
- 右上：标签制作（LabelMaker）
- 按钮行：Run / Stop / Record / Save Video
- 左下：运行输出（OutputPanel）
- 右下：按键映射（KeyMappingPanel）
"""

import gc
import inspect
import os
import time
os.environ['SDL_VIDEO_CENTERED'] = '1'

import pygame
import cv2
import json
import base64
import numpy as np
import threading
from typing import Optional, Tuple

from modules.video_module import VideoModule
from modules.label_maker import LabelMaker
from modules.output_panel import OutputPanel
from modules.key_mapping import KeyMappingPanel

current_gui = None

from easycon import EasyConController, GamePadKey, ScriptContext
from easycon.config import get

from .script_engine import ScriptEngine

from vision import (
    ocr_pokemon as ocr_pokemon_vision,
    ocr_elevated as ocr_elevated_vision,
    ocr_caught_info as ocr_caught_info_vision,
    ocr_caught_iv as ocr_caught_iv_vision,
    ocr_custom as ocr_custom_vision,
    ocr_taken_item as ocr_taken_item_vision,
    ocr_pokemon_name as ocr_pokemon_name_vision,
    classify_screen_type as classify_screen_type,
    get_all_roi_boxes as get_all_roi_boxes,
    check_service as check_service,
    check_vllm_service as check_vllm_service,
    check_ollama_service as check_ollama_service,
    check_siliconflow_service as check_siliconflow_service,
    set_model_type as set_model_type,
    get_current_model_type as get_current_model_type,
    get_available_model_types as get_available_model_types,
    get_vllm_model as get_vllm_model,
    identify_pokemon as identify_pokemon_vision,
    preload_sprites as preload_sprites,
)

from vision.ocr import MODEL_TYPE_VLLM, MODEL_TYPE_OLLAMA, MODEL_TYPE_SILICONFLOW, OLLAMA_MODEL_NAME, SILICONFLOW_MODEL, VLLM_MODEL_NAME


class EasyConGUI:
    """EasyCon 主GUI类 - 整合所有模块"""
    
    def __init__(self, script_path=None):
        # 初始化pygame
        pygame.init()
        pygame.display.init()
        pygame.key.set_repeat(300, 50)
        
        # 窗口设置
        self.window_width = 1030
        self.window_height = 790
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.DOUBLEBUF
        )
        pygame.display.set_caption("PyEasyCon")

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sprites", "shiny", "137.png")
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
            max_x = min(w-1, max_x + pad)
            max_y = min(h-1, max_y + pad)
            crop_w = max_x - min_x + 1
            crop_h = max_y - min_y + 1
            cropped = icon_surf.subsurface((min_x, min_y, crop_w, crop_h))
            icon_final = pygame.transform.smoothscale(cropped, (64, 64))
            pygame.display.set_icon(icon_final)

        # 字体（等宽字体，用于输出面板和按键映射对齐显示）
        font_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        mono_path = os.path.join(font_dir, "NotoSansMonoCJKsc-Regular.otf")
        sans_path = os.path.join(font_dir, "NotoSansCJKsc-Regular.otf")
        self.font_mono = pygame.font.Font(mono_path, 15) if os.path.exists(mono_path) else pygame.font.Font(sans_path, 15)
        self.font_mono_small = pygame.font.Font(mono_path, 12) if os.path.exists(mono_path) else pygame.font.Font(sans_path, 12)
        # 标题用普通字体
        self.font = pygame.font.Font(sans_path, 14)
        self.font_small = pygame.font.Font(sans_path, 12)
        
        # 控制器
        self.controller: Optional[EasyConController] = None

        self.button_map = {
            'A': GamePadKey.A, 'B': GamePadKey.B, 'X': GamePadKey.X, 'Y': GamePadKey.Y,
            'L': GamePadKey.L, 'R': GamePadKey.R, 'ZL': GamePadKey.ZL, 'ZR': GamePadKey.ZR,
            'PLUS': GamePadKey.PLUS, 'MINUS': GamePadKey.MINUS,
            'HOME': GamePadKey.HOME, 'CAPTURE': GamePadKey.CAPTURE,
            'UP': GamePadKey.TOP, 'DOWN': GamePadKey.DOWN,
            'LEFT': GamePadKey.LEFT, 'RIGHT': GamePadKey.RIGHT,
        }
        
        # ============== 模块初始化 ==============
        
        # 左上：游戏画面
        self.video_module = VideoModule(10, 10, 640, 360)
        
        # 右上：标签制作
        self.label_maker = LabelMaker(660, 10, 360, 360)
        self.label_maker.capture_callback = self.capture_for_label
        
        # 左下：运行输出
        self.output_panel = OutputPanel(10, 382, 640, 398)
        
        # 右下：按键映射
        self.key_mapping = KeyMappingPanel(660, 382, 360, 398)
        # 同步按键映射到 VideoModule
        self.sync_keymap_to_video()

        self.script_code = ""
        self.label_debug_saved = set()
        
        # 运行状态
        self.running = False
        self.clock = pygame.time.Clock()
        self.focused_module = 'video'
        
        # ============== 录像状态 ==============
        self.recording = False
        self.script_running = False
        self.record_fps = 30

        # 缩放后帧缓存（避免 OCR 反复调用时重复 cv2.resize）
        self.cached_1080p_frame: Optional[np.ndarray] = None
        self.cached_1080p_age: float = -1.0

        # ============== 按钮（LabelMaker 风格：64x28, border_radius=3，放在输出面板标题行右侧） ==============
        btn_w = 64
        btn_h = 28
        gap = 8
        # 输出面板标题栏：x=10, y=382, title_h=30
        btn_y = 388
        # LabelMaker 风格：等间距右对齐
        btn_right = 10 + 640 - 10  # 输出面板右边界
        positions = [btn_right - (btn_w + gap) * (i + 1) + gap for i in range(4)]
        self.btn_rects = {
            'save':   pygame.Rect(positions[0], btn_y, btn_w, btn_h),
            'record': pygame.Rect(positions[1], btn_y, btn_w, btn_h),
            'stop':   pygame.Rect(positions[2], btn_y, btn_w, btn_h),
            'run':    pygame.Rect(positions[3], btn_y, btn_w, btn_h),
        }
        self.btn_pressed = None
        self.btn_pressed_frames = 0
        
        # 脚本引擎
        self.script_engine = ScriptEngine(log_func=self.output_panel.log)
        self.script_engine.set_code_getter(lambda: self.script_code)
        self.script_engine.set_on_running_change(self.on_script_running_change)

        if script_path and os.path.exists(script_path):
            with open(script_path, 'r', encoding='utf-8') as f:
                self.script_code = f.read()
        
        # 初始化控制器和视频（在模块创建之后）
        self.init_controller()
        self.init_vllm_status()
        
        # 创建脚本执行上下文
        self.ctx = ScriptContext(
            controller=self.controller,
            get_frame=self.get_video_frame,
            log_func=self.log,
            is_running_func=self.script_engine.is_running,
            ocr_pokemon_func=self.ocr_pokemon,
            ocr_elevated_func=self.ocr_elevated,
            ocr_caught_info_func=self.ocr_caught_info,
            ocr_caught_iv_func=self.ocr_caught_iv,
            ocr_custom_func=self.ocr_custom,
            ocr_taken_item_func=self.ocr_taken_item,
            identify_pokemon_func=self.identify_pokemon,
            ocr_name_func=self.ocr_name,
        )
        
        # 注册为全局 GUI 实例，使模块级 API 函数可用
        global current_gui
        current_gui = self
    
    def sync_keymap_to_video(self):
        """将按键映射面板的当前映射同步到 VideoModule"""
        km = self.key_mapping.get_pygame_keymap()
        self.video_module.key_map = km

    # ============== 录像 ==============
    
    def start_recording(self):
        """开始录制视频"""
        if self.recording:
            self.output_panel.log("已在录制中")
            return

        frame = self.video_module.get_raw_frame()
        if frame is None:
            self.output_panel.log("无法开始录制：采集卡未就绪")
            return

        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.record_path = os.path.join(os.getcwd(), f"easycon_record_{ts}.mp4")
        self.video_writer = cv2.VideoWriter(self.record_path, fourcc, self.record_fps, (w, h))
        if not self.video_writer.isOpened():
            self.output_panel.log("录制失败：无法创建视频文件")
            self.video_writer = None
            return

        self.recording = True
        self.record_frame_interval = 60.0 / self.record_fps
        self.output_panel.log(f"开始录制: {self.record_path}")

    def stop_and_save(self):
        """停止录制并保存视频"""
        if not self.recording:
            self.output_panel.log("未在录制中")
            return

        self.recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        self.output_panel.log(f"视频已保存: {self.record_path}")
    
    def init_controller(self):
        """初始化控制器（后台线程）"""
        def controller_worker():
            try:
                import serial.tools.list_ports
                self.output_panel.log("正在搜索EasyCon控制器...")
                
                self.controller = EasyConController()
                self.video_module.set_controller(self.controller)
                if hasattr(self, 'ctx') and self.ctx is not None:
                    self.ctx.controller_ref = self.controller
                
                ports = list(serial.tools.list_ports.comports())
                
                for port in ports:
                    try:
                        if self.controller.connect(port.device, timeout=2.0):
                            self.output_panel.log(f"控制器已连接: {port.device}")
                            self.video_module.update_connection_status()
                            return
                    except:
                        continue
                
                self.output_panel.log("未找到EasyCon控制器，按键时将自动重连")
            except Exception as e:
                self.output_panel.log(f"控制器错误: {e}")
        
        threading.Thread(target=controller_worker, daemon=True).start()
    
    def init_vllm_status(self):
        """检查 VL 模型服务状态"""
        def check_worker():
            vllm_ok = check_vllm_service()
            ollama_ok = check_ollama_service()
            siliconflow_ok = check_siliconflow_service()

            vllm_short = VLLM_MODEL_NAME.replace('\\', '/').split('/')[-1]
            ollama_short = OLLAMA_MODEL_NAME
            siliconflow_short = SILICONFLOW_MODEL

            if vllm_ok:
                self.output_panel.log(f"vLLM ({vllm_short}) 可用")
            else:
                self.output_panel.log(f"vLLM (无) 不可用")

            if ollama_ok:
                self.output_panel.log(f"Ollama ({ollama_short}) 可用")
            else:
                self.output_panel.log(f"Ollama (无) 不可用")

            if siliconflow_ok:
                self.output_panel.log(f"SiliconFlow ({siliconflow_short}) 可用")
            else:
                self.output_panel.log(f"SiliconFlow (无) 不可用")

            available = get_available_model_types()
            if MODEL_TYPE_VLLM in available:
                set_model_type(MODEL_TYPE_VLLM)
                self.output_panel.log(f"VL模型: vLLM ({vllm_short})")
            elif MODEL_TYPE_OLLAMA in available:
                set_model_type(MODEL_TYPE_OLLAMA)
                self.output_panel.log(f"VL模型: {ollama_short} (Ollama)")
            elif MODEL_TYPE_SILICONFLOW in available:
                set_model_type(MODEL_TYPE_SILICONFLOW)
                self.output_panel.log(f"VL模型: {siliconflow_short} (SiliconFlow)")
            else:
                self.output_panel.log("VL模型: 无可用")

        threading.Thread(target=check_worker, daemon=True).start()
    
    # ============== 脚本执行 ==============
    
    def on_script_running_change(self, is_running: bool):
        self.script_running = is_running
    
    def run_script(self):
        if self.ctx.controller_ref is None and self.controller is not None:
            self.ctx.controller_ref = self.controller
        frame = self.video_module.get_raw_frame()
        if frame is not None:
            cap_w = get("capture", {}).get("width", 1920)
            cap_h = get("capture", {}).get("height", 1080)
            self.output_panel.log(f"采集卡原始分辨率: {frame.shape[1]}x{frame.shape[0]}")
            if (frame.shape[1], frame.shape[0]) != (cap_w, cap_h):
                self.ctx.log(f"自动缩放画面至: {cap_w}x{cap_h}")
                self.ctx.log(f"若脚本出错请检查标签匹配度")
        self.script_engine.run(self.ctx)
    
    def stop_script(self):
        self.script_engine.stop()
    
    # ============== 脚本API ==============
    
    def press(self, button: str, duration_ms: int = 50):
        """按下按钮"""
        if self.controller and self.controller.is_connected:
            try:
                key = self.button_map.get(button.upper())
                if key:
                    self.controller.click(key, duration_ms)
            except Exception as e:
                self.output_panel.log(f"按键失败: {e}")

    def hold(self, button: str):
        """按住按钮（不释放）"""
        if self.controller and self.controller.is_connected:
            key = self.button_map.get(button.upper())
            if key:
                self.controller.press(key)

    def release(self, button: str):
        """释放按钮"""
        if self.controller and self.controller.is_connected:
            key = self.button_map.get(button.upper())
            if key:
                self.controller.release(key)

    def lstick(self, x: int, y: int, duration_ms: int = 50):
        """左摇杆"""
        if self.controller and self.controller.is_connected:
            self.controller.lstick(x, y, duration_ms)

    def capture(self):
        """截图"""
        if self.controller and self.controller.is_connected:
            self.controller.capture()
    
    def wait(self, ms: int):
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if not self.script_engine.is_running():
                raise SystemExit("脚本已停止")
            time.sleep(0.05)

    def log(self, msg: str):
        """输出日志"""
        self.output_panel.log(msg)
    
    def search_label(self, label_name: str, threshold: int = 80, debug: bool = False):
        """搜索标签。threshold=-1 返回匹配度(int)，否则返回是否找到(bool)。"""
        try:
            import os
            label_path = os.path.join("assets", "labels", f"{label_name}.IL")
            if not os.path.exists(label_path):
                if debug: self.output_panel.log(f"  [label] {label_name} -> 文件不存在")
                return 0 if threshold == -1 else False

            with open(label_path, 'r', encoding='utf-8') as f:
                label_data = json.load(f)

            # 优先复用 update() 缓存的原始帧，避免重复 IO
            frame = self.video_module.get_raw_frame()
            if frame is None:
                cap = self.video_module.cap
                if cap is None or not cap.isOpened():
                    return False, 0
                ret, frame = cap.read()
                if not ret:
                    return False, 0

            if not label_data.get('ImgBase64'):
                return False, 0

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

            # 极低匹配度时才保存调试截图（纯 hash 文件名避免乱码）
            if debug and match_degree < 30 and label_name not in self.label_debug_saved:
                self.label_debug_saved.add(label_name)
                import os as _os, hashlib
                _os.makedirs("debug_label", exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                h = hashlib.md5(label_name.encode()).hexdigest()[:8]
                roi_path = f"debug_label/{ts}_{h}_roi_{match_degree:.0f}pct.png"
                tpl_path = f"debug_label/{ts}_{h}_tpl.png"
                frm_path = f"debug_label/{ts}_{h}_frame.png"
                cv2.imencode('.png', roi)[1].tofile(roi_path)
                cv2.imencode('.png', template)[1].tofile(tpl_path)
                cv2.imencode('.png', frame)[1].tofile(frm_path)
                self.output_panel.log(f"  [debug] saved: {h} ({label_name})")

            if debug:
                marker = "*" if found else " "
                self.output_panel.log(f"  [{marker}] {label_name} = {match_degree:.1f}% (threshold={threshold})")
            return degree_int if threshold == -1 else found

        except Exception as e:
            if debug: self.output_panel.log(f"  [label] {label_name} -> 错误: {e}")
            return 0 if threshold == -1 else False
    
    def get_video_frame(self, fresh: bool = False):
        """获取采集卡帧，统一规范化为 1920×1080。
        
        缓存缩放后的帧：同一次 OCR 周期内反复调用不重复 resize。
        fresh=True 时强制重新读取。
        """
        raw_age = self.video_module.get_raw_frame_age()

        # 缓存在有效期内直接复用
        if not fresh and 0 <= raw_age < 0.05:
            if self.cached_1080p_frame is not None and abs(self.cached_1080p_age - raw_age) < 0.001:
                return self.cached_1080p_frame

        # 需要新建帧
        if not fresh and 0 <= raw_age < 0.05:
            frame = self.video_module.get_raw_frame()
        else:
            cap = self.video_module.cap
            if cap is None or not cap.isOpened():
                return None
            ret, frame = cap.read()
            if not ret or frame is None:
                return None

        if frame.shape[1] != 1920 or frame.shape[0] != 1080:
            self.cached_1080p_frame = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_LINEAR)
        else:
            self.cached_1080p_frame = frame
        self.cached_1080p_age = raw_age
        return self.cached_1080p_frame
    
    def identify_pokemon(self, candidates=None, threshold=0.0):
        """识别画面中的宝可梦。返回 (species_id, score, is_shiny)。"""
        frame = self.get_video_frame()
        if frame is None:
            self.output_panel.log("识别失败: 采集卡未就绪")
            return None, 0.0, False
        result = identify_pokemon_vision(
            frame, candidates=candidates, threshold=threshold
        )
        species_id, score, is_shiny = result[0], result[1], result[2]
        if species_id is not None:
            shiny_str = "异色" if is_shiny else "普通"
            self.output_panel.log(f"识别结果: #{species_id} ({shiny_str}), 分数={score:.3f}")
        return species_id, score, is_shiny
    
    def ocr_name(self, candidates=None):
        """OCR 识别画面中的宝可梦英文名。"""
        frame = self.get_video_frame()
        if frame is None:
            return None
        name = ocr_pokemon_name_vision(frame, candidates or [], debug=False)
        if name and name.upper() != 'NONE':
            self.output_panel.log(f"OCR 验证: {name}")
        return name if name and name.upper() != 'NONE' else None
    
    def ocr_pokemon(self):
        """自动检测画面并 OCR"""
        frame = self.get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪，请等待视频画面出现后重试")
            return None
        result = ocr_pokemon_vision(frame)
        if result.get('screen') == 'UNKNOWN':
            import cv2, os
            os.makedirs('debug_ocr', exist_ok=True)
            cv2.imwrite('debug_ocr/03_unknown_frame.png', frame)
            from vision.ocr import classify_screen_type
            classify_screen_type(frame, debug=True)
        return result

    def ocr_elevated(self):
        """Elevated IV 界面 OCR"""
        frame = self.get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = ocr_elevated_vision(frame)
        return result

    def ocr_caught_info(self):
        """Caught Info 界面 OCR"""
        frame = self.get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = ocr_caught_info_vision(frame)
        return result

    def ocr_caught_iv(self):
        """Caught IV 界面 OCR"""
        frame = self.get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = ocr_caught_iv_vision(frame)
        return result

    def ocr_custom(self, image, prompt: str, model_type: str = None):
        self.output_panel.log(f"自定义 OCR: {prompt[:40]}...")
        result = ocr_custom_vision(image, prompt, model_type)
        if result:
            self.output_panel.log(f"OCR 结果: {result}")
        return result

    def ocr_taken_item(self, frame):
        return ocr_taken_item_vision(frame)

    def log_ocr_result(self, result: dict):
        screen_type = result.get('screen', '')
        if screen_type:
            self.output_panel.log(f"Screen: {screen_type}")

        order = ['level', 'gender', 'nature', 'ability',
                 'hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
        labels = {
            'level': '等级', 'gender': '性别', 'nature': '性格', 'ability': '特性',
            'hp': 'HP', 'attack': '攻击', 'defense': '防御',
            'sp_atk': '特攻', 'sp_def': '特防', 'speed': '速度',
        }
        iv_keys = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
        iv_parts = []
        for key in order:
            val = result.get(key)
            if val:
                if key in iv_keys:
                    iv_parts.append(f"{labels[key]}: {val}")
                else:
                    self.output_panel.log(f"  {labels[key]}: {val}")
        if iv_parts:
            self.output_panel.log(f"  个体值: {' | '.join(iv_parts)}")
    
    def toggle_model_type(self):
        """切换VL模型类型"""
        cur = get_current_model_type()
        available = get_available_model_types()

        if len(available) <= 1:
            self.output_panel.log("只有一个模型可用，无法切换")
            return

        current_index = available.index(cur) if cur in available else -1
        next_index = (current_index + 1) % len(available)
        next_model = available[next_index]

        set_model_type(next_model)
        vllm_short = VLLM_MODEL_NAME.replace('\\', '/').split('/')[-1]
        if next_model == MODEL_TYPE_VLLM:
            self.output_panel.log(f"VL模型: vLLM ({vllm_short})")
        elif next_model == MODEL_TYPE_OLLAMA:
            self.output_panel.log(f"VL模型: {OLLAMA_MODEL_NAME} (Ollama)")
        elif next_model == MODEL_TYPE_SILICONFLOW:
            self.output_panel.log(f"VL模型: {SILICONFLOW_MODEL} (SiliconFlow)")
    
    def capture_for_label(self):
        """为标签制作模块截图 - 使用规范化后的 1920×1080 帧，确保跨分辨率兼容"""
        frame = self.get_video_frame()
        if frame is not None:
            result = self.label_maker.capture_frame(frame)
            if result:
                self.output_panel.log("已截图到标签制作区")
            return
        self.output_panel.log("截图失败")
    
    # ============== 按钮绘制 ==============
    
    def draw_button(self, screen: pygame.Surface, font: pygame.font.Font, btn_name: str, text: str):
        """绘制按钮（LabelMaker 风格：64x28, border_radius=3, 1px border）。
        根据运行/录制状态自动配色；不适用的状态灰化但可点击。"""
        rect = self.btn_rects[btn_name]
        mx, my = pygame.mouse.get_pos()

        # 根据状态决定基础颜色
        if btn_name == 'run':
            color = (80, 80, 80) if self.script_running else (60, 120, 80)
        elif btn_name == 'stop':
            color = (120, 60, 60) if self.script_running else (80, 80, 80)
        elif btn_name == 'record':
            if self.recording:
                color = (200, 60, 60)
            else:
                color = (180, 120, 40)
        elif btn_name == 'save':
            color = (60, 80, 120) if self.recording else (80, 80, 80)
        else:
            color = (60, 60, 60)

        # 悬停加亮
        c = tuple(min(255, v + 20) for v in color) if rect.collidepoint(mx, my) else color

        # 按压加亮更多
        if self.btn_pressed == btn_name and self.btn_pressed_frames > 0:
            c = tuple(min(255, v + 40) for v in c)

        pygame.draw.rect(screen, c, rect, border_radius=3)
        pygame.draw.rect(screen, (150, 150, 150), rect, 1, border_radius=3)

        # 录制中状态：Record 按钮文字闪烁
        if btn_name == 'record' and self.recording:
            text_to_show = "Stop" if int(time.time() * 2) % 2 == 0 else "Record"
        else:
            text_to_show = text

        text_surf = font.render(text_to_show, True, (220, 220, 220))
        text_rect = text_surf.get_rect(center=rect.center)
        screen.blit(text_surf, text_rect)

    # ============== 主循环 ==============
    
    def run(self):
        self.running = True
        frame_count = 0
        last_record_frame = 0
        last_gc = time.time()
        last_cap_restart = time.time()

        self.output_panel.log("EasyCon GUI 已启动")
        self.output_panel.log("F5运行 | F6停止 | F9切换模型 | ESC退出")

        while self.running:
            # 每 60 秒强制 GC，释放累积的临时 numpy 数组
            now = time.time()
            if now - last_gc > 60:
                gc.collect()
                last_gc = now

            # 每 10 分钟重启采集卡，防止 DShow 内部缓冲区缓慢泄漏
            if now - last_cap_restart > 600 and not self.script_running:
                cap = self.video_module.cap
                if cap and cap.isOpened():
                    cap.release()
                self.video_module.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if self.video_module.cap.isOpened():
                    self.video_module.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.cached_1080p_frame = None
                last_cap_restart = now
            # 始终采集 raw_frame 供脚本 OCR 使用；可见时才渲染 pygame Surface
            window_active = pygame.display.get_active()
            if frame_count % 2 == 0:
                self.video_module.update(render=window_active)

            events = pygame.event.get()
            mouse_x, mouse_y = pygame.mouse.get_pos()
            mouse_pressed = pygame.mouse.get_pressed()

            # ========= 全局键盘事件 =========
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_F5:
                        self.run_script()
                    elif event.key == pygame.K_F6:
                        self.stop_script()
                    elif event.key == pygame.K_F9:
                        self.toggle_model_type()

            # ========= 按钮和焦点切换 =========
            for event in events:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    prev = self.focused_module

                    # 焦点区域
                    if 10 <= mx <= 650 and 10 <= my <= 370:
                        self.focused_module = 'video'
                    elif 660 <= mx <= 1020 and 10 <= my <= 370:
                        self.focused_module = 'label'
                    elif 10 <= mx <= 650 and 382 <= my <= 780:
                        self.focused_module = 'output'
                    elif 660 <= mx <= 1020 and 382 <= my <= 780:
                        self.focused_module = 'keymap'

                    if self.focused_module != prev:
                        self.video_module.focused = (self.focused_module == 'video')

                    # 按钮逻辑
                    for btn_name, btn_rect in self.btn_rects.items():
                        if btn_rect.collidepoint(mx, my):
                            self.btn_pressed = btn_name
                            self.btn_pressed_frames = 10
                            if btn_name == 'run':
                                self.run_script()
                            elif btn_name == 'stop':
                                self.stop_script()
                            elif btn_name == 'record':
                                if self.recording:
                                    self.stop_and_save()
                                else:
                                    self.start_recording()
                            elif btn_name == 'save':
                                if self.recording:
                                    self.stop_and_save()
                                else:
                                    self.output_panel.log("当前未在录制，无需保存")

            # ========= LabelMaker 事件 =========
            for event in events:
                result = self.label_maker.handle_event(event)
                if result == 'capture':
                    self.capture_for_label()
                elif isinstance(result, str):
                    self.output_panel.log(result)

            # ========= VideoModule 事件 =========
            if self.focused_module == 'video':
                for event in events:
                    self.video_module.handle_event(event)

            # ========= KeyMapping 事件 =========
            for event in events:
                keymap_result = self.key_mapping.handle_event(event)
                if keymap_result:
                    if keymap_result.startswith("keymap:"):
                        msg = keymap_result[len("keymap:"):].strip()
                        if msg:
                            self.output_panel.log(f"[按键映射] {msg}")
                        # 同步到 VideoModule
                        self.sync_keymap_to_video()

            # ========= OutputPanel 滚动事件 =========
            for event in events:
                output_rect = self.output_panel.get_rect()
                if output_rect.collidepoint(pygame.mouse.get_pos()):
                    self.output_panel.handle_event(event)

            # ========= 录像写入 =========
            if self.recording and self.video_writer and self.video_writer.isOpened():
                raw = self.video_module.get_raw_frame()
                if raw is not None:
                    now_ts = time.time()
                    if now_ts - last_record_frame >= self.record_frame_interval:
                            self.video_writer.write(raw)
                            last_record_frame = now_ts

            # ========= 按钮按压状态递减 =========
            if self.btn_pressed_frames > 0:
                self.btn_pressed_frames -= 1
                if self.btn_pressed_frames <= 0:
                    self.btn_pressed = None

            # ========= 绘制 =========
            self.screen.fill((35, 35, 40))

            # 视频模块
            self.video_module.draw(self.screen, self.font)

            # 标签制作
            self.label_maker.draw(self.screen, self.font, self.font_small)

            # 输出面板
            self.output_panel.draw(self.screen, self.font, self.font_mono_small)

            # 按键映射面板
            self.key_mapping.draw(self.screen, self.font, self.font_mono_small)

            # 四个按钮（LabelMaker 风格，覆盖在输出面板标题行右侧）
            self.draw_button(self.screen, self.font_mono_small, 'run',    "Run")
            self.draw_button(self.screen, self.font_mono_small, 'stop',   "Stop")
            self.draw_button(self.screen, self.font_mono_small, 'record', "Record")
            self.draw_button(self.screen, self.font_mono_small, 'save',   "Save")

            # 焦点边框
            focus_color = (0, 180, 240)
            focus_rects = {
                'video':  (10, 10, 640, 360),
                'label':  (660, 10, 360, 360),
                'output': (10, 382, 640, 398),
                'keymap': (660, 382, 360, 398),
            }
            if self.focused_module in focus_rects:
                pygame.draw.rect(self.screen, focus_color,
                               focus_rects[self.focused_module], 2)

            pygame.display.flip()
            frame_count += 1
            self.clock.tick(60)

        # 停止录制（如果还在录制中）
        if self.recording:
            self.stop_and_save()
        self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        self.script_running = False
        self.cached_1080p_frame = None
        
        if self.controller:
            try:
                self.controller.release_all()
                self.controller.disconnect()
            except:
                pass
        
        self.video_module.release()
        gc.collect()
        
        pygame.quit()


# ============== 模块级 API 函数（供脚本 from gui import ...） ==============

def press(button: str, duration_ms: int = 50):
    if current_gui:
        current_gui.press(button, duration_ms)

def hold(button: str):
    if current_gui:
        current_gui.hold(button)

def release(button: str):
    if current_gui:
        current_gui.release(button)

def lstick(x: int, y: int, duration_ms: int = 50):
    if current_gui:
        current_gui.lstick(x, y, duration_ms)

def capture():
    if current_gui:
        current_gui.capture()

def wait(ms: int):
    if current_gui:
        current_gui.wait(ms)

def log(msg: str):
    if current_gui:
        current_gui.log(msg)

def search_label(label_name: str, threshold: int = 80, debug: bool = False):
    if current_gui:
        return current_gui.search_label(label_name, threshold, debug)
    return 0 if threshold == -1 else False

def get_frame():
    if current_gui:
        return current_gui.get_video_frame()
    return None

def is_running():
    if current_gui is None:
        return False
    return current_gui.script_engine.is_running()

def ocr_pokemon():
    if current_gui:
        return current_gui.ocr_pokemon()
    return None

def ocr_elevated():
    if current_gui:
        return current_gui.ocr_elevated()
    return None

def ocr_caught_info():
    if current_gui:
        return current_gui.ocr_pokemon()
    return None

def ocr_caught_iv():
    if current_gui:
        return current_gui.ocr_caught_iv()
    return None

def ocr_custom(image, prompt: str, model_type: str = None):
    if current_gui:
        return current_gui.ocr_custom(image, prompt, model_type)
    return None

def identify_pokemon(candidates=None, threshold=0.0):
    if current_gui:
        return current_gui.identify_pokemon(candidates=candidates, threshold=threshold)
    return None, 0.0, False

def ocr_name_api(candidates=None):
    if current_gui:
        return current_gui.ocr_name(candidates=candidates)
    return None

def run_script(script_func):
    caller_path = inspect.stack()[1].filename
    script_path = caller_path if os.path.isfile(caller_path) and caller_path.endswith('.py') else None
    gui = EasyConGUI(script_path=script_path)
    gui.script_engine.set_script_func(script_func)
    if script_path:
        gui.output_panel.log(f"已加载: {os.path.basename(script_path)}")
    gui.output_panel.log("按 F5 运行 | F6 停止 | ESC 退出")
    gui.run()

def main():
    """启动 GUI 编辑器模式（python gui.py）"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(project_root, "demo_script.py")
    gui = EasyConGUI(script_path=script_path if os.path.exists(script_path) else None)
    gui.run()

if __name__ == "__main__":
    main()