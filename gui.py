"""
EasyCon GUI - 模块化版本
布局：
- 左上：游戏画面（VideoModule）
- 左下：脚本编辑器（ScriptEditor）
- 右上：标签制作（LabelMaker）
- 右下：运行输出（OutputPanel）
"""

import os
import time
os.environ['SDL_VIDEO_CENTERED'] = '1'

import pygame
import cv2
import json
import base64
import numpy as np
import threading
import ctypes
from typing import Optional, Tuple

# 导入模块
from modules.video_module import VideoModule
from modules.label_maker import LabelMaker
from modules.script_editor import ScriptEditor
from modules.output_panel import OutputPanel

# 模块级全局 GUI 实例引用（供模块级 API 函数使用）
_current_gui = None

from easycon_api import EasyConController, GamePadKey

from modules.pokemon_ocr import (
    ocr_pokemon as _ocr_pokemon_module,
    ocr_elevated as _ocr_elevated_module,
    ocr_caught_info as _ocr_caught_info_module,
    ocr_caught_iv as _ocr_caught_iv_module,
    ocr_custom as _ocr_custom_module,
    ocr_pokemon_name as _ocr_pokemon_name_module,
    get_vllm_model, 
    set_model_type, get_current_model_type, get_available_model_types,
    check_vllm_service, check_glm_service,
    MODEL_TYPE_VLLM, MODEL_TYPE_GLM, GLM_MODEL,
)

from modules.pokemon_sprite import identify_pokemon as _identify_pokemon_module


class EasyConGUI:
    """EasyCon 主GUI类 - 整合所有模块"""
    
    def __init__(self):
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
        pygame.display.set_caption("EasyCon - 宝可梦自动化工具")
        
        # 字体
        try:
            self.font = pygame.font.SysFont("microsoft YaHei", 14)
            self.font_small = pygame.font.SysFont("microsoft YaHei", 12)
            self.font_mono = pygame.font.SysFont("simsun", 13)
        except:
            self.font = pygame.font.Font(None, 14)
            self.font_small = pygame.font.Font(None, 12)
            self.font_mono = pygame.font.Font(None, 13)
        
        # 控制器
        self.controller: Optional[EasyConController] = None

        self._button_map = {
            'A': GamePadKey.A, 'B': GamePadKey.B, 'X': GamePadKey.X, 'Y': GamePadKey.Y,
            'L': GamePadKey.L, 'R': GamePadKey.R, 'ZL': GamePadKey.ZL, 'ZR': GamePadKey.ZR,
            'PLUS': GamePadKey.PLUS, 'MINUS': GamePadKey.MINUS,
            'HOME': GamePadKey.HOME, 'CAPTURE': GamePadKey.CAPTURE,
            'UP': GamePadKey.TOP, 'DOWN': GamePadKey.DOWN,
            'LEFT': GamePadKey.LEFT, 'RIGHT': GamePadKey.RIGHT,
        }
        
        # 初始化各个模块（先创建所有模块）
        # 左上：游戏画面
        self.video_module = VideoModule(10, 10, 640, 360)
        
        # 左下：脚本编辑器
        self.script_editor = ScriptEditor(10, 380, 640, 400)
        self.script_editor.set_callbacks(
            on_run=self._run_script,
            on_stop=self._stop_script,
            on_save=self._save_script,
            on_load=self._load_script
        )
        
        # 右上：标签制作
        self.label_maker = LabelMaker(660, 10, 360, 360)
        
        # 右下：运行输出（宽度与标签制作一致）
        self.output_panel = OutputPanel(660, 380, 360, 400)

        self._label_debug_saved = set()
        
        # 运行状态
        self.running = False
        self.clock = pygame.time.Clock()
        self.script_thread: Optional[threading.Thread] = None
        self.script_running = False
        self.stop_event = threading.Event()  # 新增：Event 来通知停止
        self._script_func = None  # 外部注册的脚本函数（如 demo_script.py 的 main）
        self._focused_module = 'video'  # 当前聚焦的模块: 'video'|'script'|'label'|'output'
        
        # 初始化控制器和视频（在模块创建之后）
        self._init_controller()
        self._init_vllm_status()
        
        # 注册为全局 GUI 实例，使模块级 API 函数可用
        global _current_gui
        _current_gui = self
    
    def _init_controller(self):
        """初始化控制器（后台线程）"""
        def controller_worker():
            try:
                import serial.tools.list_ports
                self.output_panel.log("正在搜索EasyCon控制器...")
                
                self.controller = EasyConController()
                self.video_module.set_controller(self.controller)
                
                ports = list(serial.tools.list_ports.comports())
                
                for port in ports:
                    try:
                        if self.controller.connect(port.device, timeout=1.0):
                            self.output_panel.log(f"控制器已连接: {port.device}")
                            self.video_module._update_connection_status()
                            return
                    except:
                        continue
                
                self.output_panel.log("未找到EasyCon控制器，按键时将自动重连")
            except Exception as e:
                self.output_panel.log(f"控制器错误: {e}")
        
        threading.Thread(target=controller_worker, daemon=True).start()
    
    def _init_vllm_status(self):
        """检查 VL 模型服务状态"""
        def check_worker():
            vllm_ok = check_vllm_service()
            glm_ok = check_glm_service()

            if vllm_ok:
                try:
                    model = get_vllm_model()
                    parts = model.replace('\\', '/').split('/')
                    short = '.../' + '/'.join(parts[-2:])
                    self.output_panel.log(f"vLLM 可用 ({short})")
                except Exception:
                    self.output_panel.log("vLLM 可用")
            else:
                self.output_panel.log("vLLM 未运行")

            if glm_ok:
                self.output_panel.log(f"{GLM_MODEL} 可用")
            else:
                self.output_panel.log(f"{GLM_MODEL} 不可用")

            available = get_available_model_types()
            if MODEL_TYPE_VLLM in available:
                set_model_type(MODEL_TYPE_VLLM)
                self.output_panel.log(f"VL模型: vLLM (本地)")
            elif MODEL_TYPE_GLM in available:
                set_model_type(MODEL_TYPE_GLM)
                self.output_panel.log(f"VL模型: {GLM_MODEL} (在线)")
            else:
                self.output_panel.log("VL模型: 无可用")

        threading.Thread(target=check_worker, daemon=True).start()
    
    # ============== 脚本执行 ==============
    
    def _run_script(self):
        """运行脚本"""
        if self.script_running:
            self.output_panel.log("脚本已在运行中")
            return
        
        self.script_running = True
        self.script_editor.is_running = True
        self.stop_event.clear()  # 确保 Event 是重置状态
        
        def script_worker():
            try:
                self.output_panel.log("=" * 40)
                self.output_panel.log("脚本开始运行")
                
                if self._script_func is not None:
                    # 直接调用外部注册的脚本函数（来自 run_script）
                    self._script_func()
                else:
                    # 从编辑器获取代码并通过 exec 执行
                    code = self.script_editor.get_code()
                    exec_globals = {
                        "gui": self,
                        "is_running": lambda: not self.stop_event.is_set() and self.script_running,
                        "press": self.press,
                        "hold": self.hold,
                        "release": self.release,
                        "lstick": self.lstick,
                        "capture": self.capture,
                        "wait": self.wait,
                        "log": self.log,
                        "search_label": self.search_label,
                        "ocr_pokemon": self._ocr_pokemon,
                        "ocr_elevated": self._ocr_elevated,
                        "ocr_caught_info": self._ocr_caught_info,
                        "ocr_caught_iv": self._ocr_caught_iv,
                        "ocr_custom": self._ocr_custom,
                        "get_frame": self._get_video_frame,
                    }
                    exec(code, exec_globals)

                self.output_panel.log("脚本运行完成")
            except SystemExit as e:
                self.output_panel.log(f"{e}")
            except Exception as e:
                self.output_panel.log(f"脚本错误: {e}")
                import traceback
                self.output_panel.log(traceback.format_exc())
            finally:
                self.script_running = False
                self.script_editor.is_running = False
                self.output_panel.log("=" * 40)
        
        self.script_thread = threading.Thread(target=script_worker, daemon=True)
        self.script_thread.start()
    
    def _stop_script(self):
        """停止脚本 - 彻底的解决方案"""
        self.script_running = False
        self.script_editor.is_running = False
        self.stop_event.set()  # 触发 Event
        self.output_panel.log("正在停止脚本...")
        
        # 尝试强制停止线程
        if self.script_thread and self.script_thread.is_alive():
            try:
                # 使用 ctypes 注入异常来强制停止线程
                tid = self.script_thread.ident
                if tid:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(tid),
                        ctypes.py_object(SystemExit)
                    )
                # 等待一小段时间让线程响应
                time.sleep(0.1)
                # 如果线程还在，再注入一次
                if self.script_thread.is_alive():
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(tid),
                        ctypes.py_object(SystemExit)
                    )
                    time.sleep(0.2)
            except Exception as e:
                self.output_panel.log(f"停止线程时出错: {e}")
        
        # 重置 Event
        self.stop_event.clear()
        self.output_panel.log("脚本已停止")
    
    def _save_script(self):
        """保存脚本"""
        try:
            import os
            # 生成文件名
            idx = 1
            while os.path.exists(f"script_{idx}.py"):
                idx += 1
            file_path = f"script_{idx}.py"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.script_editor.get_code())
            
            self.output_panel.log(f"脚本已保存: {file_path}")
        except Exception as e:
            self.output_panel.log(f"保存失败: {e}")
    
    def _load_script(self):
        """加载脚本"""
        try:
            import os
            script_files = [f for f in os.listdir('.') if f.startswith('script_') and f.endswith('.py')]
            if not script_files:
                self.output_panel.log("未找到脚本文件")
                return
            
            script_files.sort()
            file_path = script_files[-1]
            
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            self.script_editor.set_code(code)
            self.output_panel.log(f"脚本已加载: {file_path}")
        except Exception as e:
            self.output_panel.log(f"加载失败: {e}")
    
    # ============== 脚本API ==============
    
    def press(self, button: str, duration_ms: int = 50):
        """按下按钮"""
        if self.controller and self.controller.is_connected:
            try:
                key = self._button_map.get(button.upper())
                if key:
                    self.controller.click(key, duration_ms)
            except Exception as e:
                self.output_panel.log(f"按键失败: {e}")

    def hold(self, button: str):
        """按住按钮（不释放）"""
        if self.controller and self.controller.is_connected:
            key = self._button_map.get(button.upper())
            if key:
                self.controller.press(key)

    def release(self, button: str):
        """释放按钮"""
        if self.controller and self.controller.is_connected:
            key = self._button_map.get(button.upper())
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
        """可中断等待"""
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if self.stop_event.is_set() or not self.script_running:
                raise SystemExit("脚本已停止")
            time.sleep(0.05)

    def log(self, msg: str):
        """输出日志"""
        self.output_panel.log(msg)
    
    def search_label(self, label_name: str, threshold: int = 80, debug: bool = False):
        """搜索标签。threshold=-1 返回匹配度(int)，否则返回是否找到(bool)。"""
        try:
            import os
            label_path = os.path.join("labels", f"{label_name}.IL")
            if not os.path.exists(label_path):
                if debug: self.output_panel.log(f"  [label] {label_name} -> 文件不存在")
                return 0 if threshold == -1 else False

            with open(label_path, 'r', encoding='utf-8') as f:
                label_data = json.load(f)

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
            if debug and match_degree < 30 and label_name not in self._label_debug_saved:
                self._label_debug_saved.add(label_name)
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
    
    def _get_video_frame(self):
        """获取采集卡当前帧 (1920×1080 BGR)"""
        return self.video_module.get_raw_frame()
    
    def _identify_pokemon(self, candidates=None, threshold=0.0):
        """识别画面中的宝可梦。返回 (species_id, score, is_shiny)。"""
        frame = self._get_video_frame()
        if frame is None:
            self.output_panel.log("识别失败: 采集卡未就绪")
            return None, 0.0, False
        result = _identify_pokemon_module(
            frame, candidates=candidates, threshold=threshold
        )
        species_id, score, is_shiny = result[0], result[1], result[2]
        if species_id is not None:
            shiny_str = "异色" if is_shiny else "普通"
            self.output_panel.log(f"识别结果: #{species_id} ({shiny_str}), 分数={score:.3f}")
        return species_id, score, is_shiny
    
    def _ocr_name(self, candidates=None):
        """OCR 识别画面中的宝可梦英文名。
        candidates: 备选列表，如 ["走路草(Oddish)", "嘟嘟(Doduo)"]，None=不限定
        返回英文名或 None。
        """
        frame = self._get_video_frame()
        if frame is None:
            return None
        name = _ocr_pokemon_name_module(frame, candidates or [], debug=False)
        if name and name.upper() != 'NONE':
            self.output_panel.log(f"OCR 验证: {name}")
        return name if name and name.upper() != 'NONE' else None
    
    def _ocr_pokemon(self):
        """自动检测画面并 OCR"""
        frame = self._get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪，请等待视频画面出现后重试")
            return None
        result = _ocr_pokemon_module(frame)
        if result.get('screen') == 'UNKNOWN':
            import cv2, os
            os.makedirs('debug_ocr', exist_ok=True)
            cv2.imwrite('debug_ocr/03_unknown_frame.png', frame)
            from modules.pokemon_ocr import classify_screen_type
            classify_screen_type(frame, debug=True)
        #self._log_ocr_result(result)
        return result

    def _ocr_elevated(self):
        """Elevated IV 界面 OCR"""
        frame = self._get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = _ocr_elevated_module(frame)
        #self._log_ocr_result(result)
        return result

    def _ocr_caught_info(self):
        """Caught Info 界面 OCR"""
        frame = self._get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = _ocr_caught_info_module(frame)
        #self._log_ocr_result(result)
        return result

    def _ocr_caught_iv(self):
        """Caught IV 界面 OCR"""
        frame = self._get_video_frame()
        if frame is None:
            self.output_panel.log("OCR 失败: 采集卡未就绪")
            return None
        result = _ocr_caught_iv_module(frame)
        #self._log_ocr_result(result)
        return result

    def _ocr_custom(self, image, prompt: str, model_type: str = None):
        self.output_panel.log(f"自定义 OCR: {prompt[:40]}...")
        result = _ocr_custom_module(image, prompt, model_type)
        if result:
            self.output_panel.log(f"OCR 结果: {result}")
        return result

    def _log_ocr_result(self, result: dict):
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
    
    def _toggle_model_type(self):
        """切换VL模型类型"""
        current = get_current_model_type()
        available = get_available_model_types()

        if len(available) <= 1:
            self.output_panel.log("只有一个模型可用，无法切换")
            return

        current_index = available.index(current) if current in available else -1
        next_index = (current_index + 1) % len(available)
        next_model = available[next_index]

        set_model_type(next_model)
        if next_model == MODEL_TYPE_VLLM:
            self.output_panel.log("VL模型: vLLM (本地)")
        elif next_model == MODEL_TYPE_GLM:
            self.output_panel.log(f"VL模型: {GLM_MODEL} (在线)")
    
    def _capture_for_label(self):
        """为标签制作模块截图 - 从视频模块获取当前帧"""
        # 从视频模块获取当前帧
        if self.video_module.cap and self.video_module.cap.isOpened():
            ret, frame = self.video_module.cap.read()
            if ret:
                result = self.label_maker.capture_frame(frame)
                if result:
                    self.output_panel.log("已截图到标签制作区")
                return
        self.output_panel.log("截图失败")
    
    # ============== 主循环 ==============
    
    def run(self):
        """运行主循环"""
        self.running = True
        frame_count = 0
        
        self.output_panel.log("EasyCon GUI 已启动")
        self.output_panel.log("F5运行脚本 | F6停止 | F9切换VL模型 | ESC退出")
        
        while self.running:
            # 更新视频模块
            if frame_count % 3 == 0:
                self.video_module.update()
            
            # 处理事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_F9:
                        self._toggle_model_type()
                
                # 鼠标点击切换模块焦点
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    prev = self._focused_module
                    # 视频模块区域 (10,10 640x360)
                    if 10 <= mx <= 650 and 10 <= my <= 370:
                        self._focused_module = 'video'
                    # 脚本编辑器区域 (10,380 640x400)
                    elif 10 <= mx <= 650 and 380 <= my <= 780:
                        self._focused_module = 'script'
                    # 标签制作区域 (660,10 360x360)
                    elif 660 <= mx <= 1020 and 10 <= my <= 370:
                        self._focused_module = 'label'
                    # 运行输出区域 (660,380 360x400)
                    elif 660 <= mx <= 1020 and 380 <= my <= 780:
                        self._focused_module = 'output'
                    # 同步视频模块焦点
                    if self._focused_module != prev:
                        self.video_module.focused = (self._focused_module == 'video')
                
                # 分发事件到各个模块
                # 注意：标签制作器的输入框需要优先处理键盘事件
                handled = False
                
                # 标签制作（优先处理，因为可能有输入框激活）
                result = self.label_maker.handle_event(event)
                if result == 'capture':
                    self._capture_for_label()
                    handled = True
                elif isinstance(result, str):
                    # 保存标签的返回消息
                    self.output_panel.log(result)
                    handled = True
                elif result:
                    handled = True
                
                # 视频模块（键盘事件）
                if not handled:
                    handled = self.video_module.handle_event(event)
                
                # 脚本编辑器
                if not handled:
                    handled = self.script_editor.handle_event(event)
            
            # 绘制所有模块
            self.screen.fill((35, 35, 40))
            
            self.video_module.draw(self.screen, self.font)
            self.script_editor.draw(self.screen, self.font, self.font_mono, self.font_small)
            self.label_maker.draw(self.screen, self.font, self.font_small)
            self.output_panel.draw(self.screen, self.font, self.font_small)
            
            # 聚焦模块边框
            focus_color = (0, 180, 240)
            focus_rects = {
                'video':  (10, 10, 640, 360),
                'script': (10, 380, 640, 400),
                'label':  (660, 10, 360, 360),
                'output': (660, 380, 360, 400),
            }
            if self._focused_module in focus_rects:
                pygame.draw.rect(self.screen, focus_color,
                               focus_rects[self._focused_module], 2)
            
            pygame.display.flip()
            
            frame_count += 1
            self.clock.tick(60)
        
        self._cleanup()
    
    def _cleanup(self):
        """清理资源"""
        self.script_running = False
        
        if self.controller:
            try:
                self.controller.release_all()
                self.controller.disconnect()
            except:
                pass
        
        self.video_module.release()
        
        pygame.quit()


# ============== 模块级 API 函数（供脚本 from gui import ...） ==============

def press(button: str, duration_ms: int = 50):
    """按下按钮"""
    if _current_gui:
        _current_gui.press(button, duration_ms)

def hold(button: str):
    """按住按钮（不释放）"""
    if _current_gui:
        _current_gui.hold(button)

def release(button: str):
    """释放按钮"""
    if _current_gui:
        _current_gui.release(button)

def lstick(x: int, y: int, duration_ms: int = 50):
    """左摇杆"""
    if _current_gui:
        _current_gui.lstick(x, y, duration_ms)

def capture():
    """NS 截图"""
    if _current_gui:
        _current_gui.capture()

def wait(ms: int):
    """可中断等待（毫秒）"""
    if _current_gui:
        _current_gui.wait(ms)

def log(msg: str):
    """输出日志到 GUI"""
    if _current_gui:
        _current_gui.log(msg)

def search_label(label_name: str, threshold: int = 80, debug: bool = False):
    """搜索图像标签。threshold=-1 返回匹配度(int)，否则返回是否找到(bool)"""
    if _current_gui:
        return _current_gui.search_label(label_name, threshold, debug)
    return 0 if threshold == -1 else False

def get_frame():
    """获取采集卡当前帧 (BGR numpy array)"""
    if _current_gui:
        return _current_gui._get_video_frame()
    return None

def is_running():
    """检查脚本是否应继续运行"""
    if _current_gui is None:
        return False
    return _current_gui.script_running and not _current_gui.stop_event.is_set()

def ocr_pokemon():
    """自动检测画面并 OCR"""
    if _current_gui:
        return _current_gui._ocr_pokemon()
    return None

def ocr_elevated():
    """Elevated IV 界面 OCR"""
    if _current_gui:
        return _current_gui._ocr_elevated()
    return None

def ocr_caught_info():
    """Caught Info 界面 OCR"""
    if _current_gui:
        return _current_gui._ocr_caught_info()
    return None

def ocr_caught_iv():
    """Caught IV 界面 OCR"""
    if _current_gui:
        return _current_gui._ocr_caught_iv()
    return None

def ocr_custom(image, prompt: str, model_type: str = None):
    """自定义 VL OCR，可指定 model_type='glm' 或 'vllm'"""
    if _current_gui:
        return _current_gui._ocr_custom(image, prompt, model_type)
    return None


def identify_pokemon(candidates=None, threshold=0.0):
    """识别画面中的宝可梦。返回 (species_id, score, is_shiny)。"""
    if _current_gui:
        return _current_gui._identify_pokemon(candidates=candidates, threshold=threshold)
    return None, 0.0, False


def ocr_name(candidates=None):
    """OCR 识别画面中的宝可梦英文名。
    candidates: 备选列表如 ["走路草(Oddish)", ...]
    返回英文名或 None。
    """
    if _current_gui:
        return _current_gui._ocr_name(candidates=candidates)
    return None


def run_script(script_func):
    """脚本入口：初始化 GUI，注册脚本函数，等待用户点击运行（F5）"""
    gui = EasyConGUI()
    gui._script_func = script_func
    gui.output_panel.log("脚本已加载，按 F5 运行 | F6 停止")
    gui.run()


def main():
    """启动 GUI 编辑器模式（python gui.py）"""
    gui = EasyConGUI()
    gui.run()


if __name__ == "__main__":
    main()