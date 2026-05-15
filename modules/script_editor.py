"""
Script Editor Module - 脚本编辑器模块
Python代码编辑功能，支持语法高亮
"""

import re
import subprocess
import pygame
import os
from typing import List, Optional, Callable, Tuple

# 语法高亮
try:
    from pygments import lex
    from pygments.lexers import PythonLexer
    from pygments.token import Token
    _has_pygments = True
except ImportError:
    _has_pygments = False


# 主题色映射
TOKEN_COLORS = {
    Token.Keyword: (100, 150, 220),
    Token.Keyword.Namespace: (220, 200, 100),
    Token.Keyword.Type: (100, 200, 200),
    Token.Name.Function: (200, 200, 100),
    Token.Name.Builtin: (100, 200, 200),
    Token.Name.Decorator: (200, 180, 100),
    Token.Comment: (100, 180, 100),
    Token.String: (220, 150, 100),
    Token.String.Doc: (180, 160, 100),
    Token.Number: (180, 120, 220),
    Token.Operator: (200, 180, 60),
    Token.Name: (220, 220, 220),
}


def _token_color(token_type) -> tuple:
    """根据 token 类型获取颜色"""
    if not _has_pygments:
        return None
    ttype = token_type
    while ttype not in TOKEN_COLORS and ttype.parent is not None:
        ttype = ttype.parent
    return TOKEN_COLORS.get(ttype, (200, 200, 200))


class ScriptEditor:
    """脚本编辑器模块 - 支持常见IDE功能"""
    
    def __init__(self, x: int, y: int, width: int = 640, height: int = 400):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        
        # 代码内容
        self.lines: List[str] = []
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_script.txt")
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                self.lines = [s.replace('\r', '') for s in f.read().split('\n')]
        except FileNotFoundError:
            self.lines = ["# demo_script.txt  not found"]
        
        # 光标位置
        self.cursor_line = 0
        self.cursor_col = 0
        
        # 选择区域
        self.selection_start: Optional[Tuple[int, int]] = None
        self.selection_end: Optional[Tuple[int, int]] = None
        
        # 运行状态
        self.is_running = False
        self.on_run_callback: Optional[Callable] = None
        self.on_stop_callback: Optional[Callable] = None
        self.on_save_callback: Optional[Callable] = None
        self.on_load_callback: Optional[Callable] = None
        
        # 文件路径
        self.file_path: Optional[str] = None
        
        # 按钮
        self.buttons = {
            'run': pygame.Rect(x + 10, y + 10, 70, 28),
            'stop': pygame.Rect(x + 90, y + 10, 70, 28),
            'save': pygame.Rect(x + 170, y + 10, 60, 28),
            'load': pygame.Rect(x + 240, y + 10, 60, 28),
        }
        
        # 编辑区域
        self.editor_x = x + 10
        self.editor_y = y + 50
        self.editor_width = width - 20
        self.editor_height = height - 60
        
        # 滚动偏移
        self.scroll_y = 0
        self.line_height = 20
        
        # 历史记录（用于撤销）
        self.history: List[List[str]] = []
        self.history_index = -1
        self._save_history()
    
    def set_callbacks(self, on_run=None, on_stop=None, on_save=None, on_load=None):
        """设置回调函数"""
        self.on_run_callback = on_run
        self.on_stop_callback = on_stop
        self.on_save_callback = on_save
        self.on_load_callback = on_load
    
    def get_code(self) -> str:
        """获取完整代码"""
        return "\n".join(line.rstrip('\r') for line in self.lines)
    
    def set_code(self, code: str):
        """设置代码"""
        self.lines = [line.replace('\r', '') for line in code.split("\n")]
        self.cursor_line = min(self.cursor_line, len(self.lines) - 1)
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
        self._save_history()
    
    def _save_history(self):
        """保存历史记录"""
        # 限制历史记录数量
        if len(self.history) > 50:
            self.history = self.history[-50:]
            self.history_index = len(self.history) - 1
        
        # 删除当前位置之后的历史
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
        
        # 添加新历史
        self.history.append([line[:] for line in self.lines])
        self.history_index += 1
    
    def _undo(self):
        """撤销"""
        if self.history_index > 0:
            self.history_index -= 1
            self.lines = [line[:] for line in self.history[self.history_index]]
            self.cursor_line = min(self.cursor_line, len(self.lines) - 1)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
    
    def _redo(self):
        """重做"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.lines = [line[:] for line in self.history[self.history_index]]
            self.cursor_line = min(self.cursor_line, len(self.lines) - 1)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        处理事件
        Returns: 是否处理了该事件
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                
                # 检查按钮点击
                for btn_name, btn_rect in self.buttons.items():
                    if btn_rect.collidepoint(mx, my):
                        if btn_name == 'run' and self.on_run_callback:
                            self.on_run_callback()
                        elif btn_name == 'stop' and self.on_stop_callback:
                            self.on_stop_callback()
                        elif btn_name == 'save' and self.on_save_callback:
                            self.on_save_callback()
                        elif btn_name == 'load' and self.on_load_callback:
                            self.on_load_callback()
                        return True
                
                # 检查是否在编辑区域
                if self._is_in_editor(mx, my):
                    self._set_cursor_from_mouse(mx, my)
                    # 清除选择
                    self.selection_start = None
                    self.selection_end = None
                    return True
        
        elif event.type == pygame.KEYDOWN:
            return self._handle_key_input(event)

        elif event.type == pygame.MOUSEWHEEL:
            if self._is_in_editor(*pygame.mouse.get_pos()):
                self.scroll_y -= event.y * self.line_height * 3
                max_scroll = max(0, len(self.lines) * self.line_height - self.editor_height)
                self.scroll_y = max(0, min(self.scroll_y, max_scroll))
                return True

        return False
    
    def _is_in_editor(self, mx: int, my: int) -> bool:
        """检查坐标是否在编辑器内"""
        return (self.editor_x <= mx <= self.editor_x + self.editor_width and
                self.editor_y <= my <= self.editor_y + self.editor_height)
    
    def _set_cursor_from_mouse(self, mx: int, my: int):
        """根据鼠标位置设置光标，通过字体度量精确计算列"""
        rel_y = my - self.editor_y + self.scroll_y
        line_idx = rel_y // self.line_height
        line_idx = max(0, min(line_idx, len(self.lines) - 1))
        self.cursor_line = line_idx
        
        rel_x = mx - self.editor_x - 45
        if rel_x <= 0:
            self.cursor_col = 0
            return
        
        line = self.lines[line_idx].replace('\r', '')
        font = getattr(self, '_mono_font', None)
        if font is None:
            self.cursor_col = max(0, int(rel_x / 8))
            return
        
        cum = 0
        for col, ch in enumerate(line):
            cw = font.size(ch)[0]
            if cum + cw // 2 >= rel_x:
                self.cursor_col = col
                return
            cum += cw
        self.cursor_col = len(line)
    
    def _handle_key_input(self, event: pygame.event.Event) -> bool:
        """处理键盘输入"""
        mods = pygame.key.get_mods()
        shift_pressed = mods & pygame.KMOD_SHIFT
        ctrl_pressed = mods & pygame.KMOD_CTRL
        
        # Ctrl+Z 撤销
        if ctrl_pressed and event.key == pygame.K_z and not shift_pressed:
            self._undo()
            return True
        
        # Ctrl+Y 或 Ctrl+Shift+Z 重做
        if (ctrl_pressed and event.key == pygame.K_y) or \
           (ctrl_pressed and shift_pressed and event.key == pygame.K_z):
            self._redo()
            return True
        
        # Ctrl+C 复制
        if ctrl_pressed and event.key == pygame.K_c:
            self._copy()
            return True
        
        # Ctrl+X 剪切
        if ctrl_pressed and event.key == pygame.K_x:
            self._cut()
            return True
        
        # Ctrl+V 粘贴
        if ctrl_pressed and event.key == pygame.K_v:
            self._paste()
            return True
        
        # Ctrl+A 全选
        if ctrl_pressed and event.key == pygame.K_a:
            self.selection_start = (0, 0)
            self.selection_end = (len(self.lines) - 1, len(self.lines[-1]))
            return True
        
        # F5 运行
        if event.key == pygame.K_F5:
            if self.on_run_callback:
                self.on_run_callback()
            return True
        
        # F6 停止
        if event.key == pygame.K_F6:
            if self.on_stop_callback:
                self.on_stop_callback()
            return True
        
        # 方向键（带Shift选择）
        if event.key == pygame.K_LEFT:
            if shift_pressed:
                self._start_selection_if_needed()
            self._move_cursor_left()
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        elif event.key == pygame.K_RIGHT:
            if shift_pressed:
                self._start_selection_if_needed()
            self._move_cursor_right()
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        elif event.key == pygame.K_UP:
            if shift_pressed:
                self._start_selection_if_needed()
            self._move_cursor_up()
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        elif event.key == pygame.K_DOWN:
            if shift_pressed:
                self._start_selection_if_needed()
            self._move_cursor_down()
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        # Home键 - 行首
        elif event.key == pygame.K_HOME:
            if shift_pressed:
                self._start_selection_if_needed()
            self.cursor_col = 0
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        # End键 - 行尾
        elif event.key == pygame.K_END:
            if shift_pressed:
                self._start_selection_if_needed()
            self.cursor_col = len(self.lines[self.cursor_line])
            if shift_pressed:
                self.selection_end = (self.cursor_line, self.cursor_col)
            else:
                self._clear_selection()
            return True
        
        # 删除选中的文本
        if self._has_selection() and event.unicode and event.unicode.isprintable():
            self._delete_selection()
        
        # 回车键
        if event.key == pygame.K_RETURN:
            self._save_history()
            self._insert_newline()
            return True
        
        # 退格键
        elif event.key == pygame.K_BACKSPACE:
            self._save_history()
            if self._has_selection():
                self._delete_selection()
            else:
                self._backspace()
            return True
        
        # 删除键
        elif event.key == pygame.K_DELETE:
            self._save_history()
            if self._has_selection():
                self._delete_selection()
            else:
                self._delete()
            return True
        
        # Tab键（支持Shift+Tab反向缩进）
        elif event.key == pygame.K_TAB:
            self._save_history()
            if shift_pressed:
                self._unindent()
            else:
                self._indent()
            return True
        
        # 普通字符输入
        elif event.unicode and event.unicode.isprintable():
            self._save_history()
            self._insert_char(event.unicode)
            return True
        
        return False
    
    def _start_selection_if_needed(self):
        """如果需要，开始选择"""
        if not self._has_selection():
            self.selection_start = (self.cursor_line, self.cursor_col)
            self.selection_end = (self.cursor_line, self.cursor_col)
    
    def _clear_selection(self):
        """清除选择"""
        self.selection_start = None
        self.selection_end = None
    
    def _has_selection(self) -> bool:
        """检查是否有选中的文本"""
        return self.selection_start is not None and self.selection_end is not None
    
    def _get_selection_range(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """获取选择范围（规范化）"""
        if not self._has_selection():
            return (self.cursor_line, self.cursor_col), (self.cursor_line, self.cursor_col)
        
        start = self.selection_start
        end = self.selection_end
        
        # 规范化：确保start在end之前
        if start[0] > end[0] or (start[0] == end[0] and start[1] > end[1]):
            start, end = end, start
        
        return start, end
    
    def _delete_selection(self):
        """删除选中的文本"""
        if not self._has_selection():
            return
        
        start, end = self._get_selection_range()
        
        if start[0] == end[0]:
            # 同一行
            line = self.lines[start[0]]
            self.lines[start[0]] = line[:start[1]] + line[end[1]:]
        else:
            # 多行
            first_line = self.lines[start[0]][:start[1]]
            last_line = self.lines[end[0]][end[1]:]
            self.lines[start[0]] = first_line + last_line
            # 删除中间行
            del self.lines[start[0] + 1:end[0] + 1]
        
        self.cursor_line = start[0]
        self.cursor_col = start[1]
        self._clear_selection()

    def _get_clipboard(self):
        try:
            return subprocess.check_output(
                ['powershell', '-Command', 'Get-Clipboard'],
                timeout=2, text=True, stderr=subprocess.DEVNULL
            )
        except Exception:
            return ''

    def _set_clipboard(self, text):
        try:
            p = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            p.communicate(input=text.encode('utf-8', errors='replace'), timeout=2)
        except Exception:
            pass

    def _copy(self):
        """复制选中文本到系统剪贴板"""
        if self._has_selection():
            start, end = self._get_selection_range()
            lines = []
            if start[0] == end[0]:
                lines.append(self.lines[start[0]][start[1]:end[1]])
            else:
                lines.append(self.lines[start[0]][start[1]:])
                for i in range(start[0] + 1, end[0]):
                    lines.append(self.lines[i])
                lines.append(self.lines[end[0]][:end[1]])
            text = "\n".join(lines)
            self._set_clipboard(text)
        else:
            self._set_clipboard(self.lines[self.cursor_line])

    def _cut(self):
        """剪切选中文本"""
        self._copy()
        self._delete_selection()

    def _paste(self):
        """从系统剪贴板粘贴"""
        try:
            text = self._get_clipboard()
        except Exception:
            text = ''
        if not text:
            return
        text = text.replace('\r', '').rstrip('\n')
        if self._has_selection():
            self._delete_selection()
        self._save_history()
        line = self.lines[self.cursor_line]
        prefix = line[:self.cursor_col]
        suffix = line[self.cursor_col:]
        pasted_lines = text.split('\n')
        if len(pasted_lines) == 1:
            self.lines[self.cursor_line] = prefix + pasted_lines[0] + suffix
            self.cursor_col += len(pasted_lines[0])
        else:
            self.lines[self.cursor_line] = prefix + pasted_lines[0]
            for i in range(1, len(pasted_lines)):
                self.cursor_line += 1
                self.lines.insert(self.cursor_line, pasted_lines[i])
            self.lines[self.cursor_line] += suffix
            self.cursor_col = len(pasted_lines[-1])
        self._ensure_cursor_visible()

    @property
    def _visible_lines(self):
        return self.editor_height // self.line_height

    def _ensure_cursor_visible(self):
        top = self.scroll_y // self.line_height
        bottom = top + self._visible_lines - 1
        if self.cursor_line < top:
            self.scroll_y = self.cursor_line * self.line_height
        elif self.cursor_line > bottom:
            self.scroll_y = (self.cursor_line - self._visible_lines + 1) * self.line_height
        max_scroll = max(0, len(self.lines) * self.line_height - self.editor_height)
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

    def _move_cursor_left(self):
        """光标左移"""
        if self.cursor_col > 0:
            self.cursor_col -= 1
        elif self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])
    
    def _move_cursor_right(self):
        """光标右移"""
        if self.cursor_col < len(self.lines[self.cursor_line]):
            self.cursor_col += 1
        elif self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = 0
    
    def _move_cursor_up(self):
        """光标上移"""
        if self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._ensure_cursor_visible()

    def _move_cursor_down(self):
        """光标下移"""
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._ensure_cursor_visible()
    
    def _insert_newline(self):
        """插入新行"""
        line = self.lines[self.cursor_line]
        self.lines[self.cursor_line] = line[:self.cursor_col]
        self.lines.insert(self.cursor_line + 1, line[self.cursor_col:])
        self.cursor_line += 1
        self.cursor_col = 0
        self._ensure_cursor_visible()
    
    def _backspace(self):
        """退格"""
        if self.cursor_col > 0:
            line = self.lines[self.cursor_line]
            self.lines[self.cursor_line] = line[:self.cursor_col-1] + line[self.cursor_col:]
            self.cursor_col -= 1
        elif self.cursor_line > 0:
            line = self.lines.pop(self.cursor_line)
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])
            self.lines[self.cursor_line] += line
    
    def _delete(self):
        """删除"""
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            self.lines[self.cursor_line] = line[:self.cursor_col] + line[self.cursor_col+1:]
        elif self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines.pop(self.cursor_line + 1)
    
    def _indent(self):
        """缩进（插入4个空格）"""
        line = self.lines[self.cursor_line]
        self.lines[self.cursor_line] = line[:self.cursor_col] + "    " + line[self.cursor_col:]
        self.cursor_col += 4
    
    def _unindent(self):
        """反向缩进（删除行首最多4个空格）"""
        line = self.lines[self.cursor_line]
        # 删除光标前最多4个空格
        spaces_to_remove = 0
        for i in range(min(4, self.cursor_col)):
            if line[self.cursor_col - 1 - i] == ' ':
                spaces_to_remove += 1
            else:
                break
        
        if spaces_to_remove > 0:
            self.lines[self.cursor_line] = line[:self.cursor_col - spaces_to_remove] + line[self.cursor_col:]
            self.cursor_col -= spaces_to_remove
    
    def _insert_char(self, char: str):
        """插入字符"""
        char = char.replace('\r', '')
        if not char:
            return
        line = self.lines[self.cursor_line]
        self.lines[self.cursor_line] = line[:self.cursor_col] + char + line[self.cursor_col:]
        self.cursor_col += 1
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font, 
             mono_font: pygame.font.Font, small_font: pygame.font.Font):
        """绘制编辑器"""
        self._mono_font = mono_font
        
        # 背景
        pygame.draw.rect(screen, (30, 30, 35), (self.x, self.y, self.width, self.height))
        
        # 标题栏
        pygame.draw.rect(screen, (40, 40, 45), (self.x, self.y, self.width, 45))
        
        # 按钮
        run_color = (0, 120, 0) if not self.is_running else (60, 60, 60)
        stop_color = (120, 0, 0) if self.is_running else (60, 60, 60)
        self._draw_button(screen, small_font, 'run', "Run(F5)", run_color)
        self._draw_button(screen, small_font, 'stop', "Stop(F6)", stop_color)
        self._draw_button(screen, small_font, 'save', "Save", (80, 80, 120))
        self._draw_button(screen, small_font, 'load', "Load", (80, 80, 120))
        
        # 编辑区域背景
        pygame.draw.rect(screen, (25, 25, 30), 
                        (self.editor_x, self.editor_y, self.editor_width, self.editor_height))
        
        # 计算可见行范围
        start_line = self.scroll_y // self.line_height
        end_line = min(start_line + self.editor_height // self.line_height + 1, len(self.lines))
        
        # 获取选择范围
        sel_start, sel_end = self._get_selection_range()
        
        # 绘制代码行
        for i in range(start_line, end_line):
            y = self.editor_y + (i - start_line) * self.line_height
            
            # 行号背景
            if i == self.cursor_line:
                pygame.draw.rect(screen, (40, 40, 50), 
                               (self.editor_x, y, 40, self.line_height))
            
            # 行号
            num_color = (100, 100, 100) if i != self.cursor_line else (150, 150, 150)
            num_surf = mono_font.render(f"{i+1:3d}", True, num_color)
            screen.blit(num_surf, (self.editor_x + 5, y))
            
            # 代码内容（先清除 Windows 换行残留）
            line = self.lines[i].replace('\r', '').replace('\n', '')
            x_offset = self.editor_x + 45
            
            # 绘制选择高亮
            if self._has_selection() and sel_start[0] <= i <= sel_end[0]:
                sel_start_col = sel_start[1] if i == sel_start[0] else 0
                sel_end_col = sel_end[1] if i == sel_end[0] else len(line)
                
                if sel_start_col < sel_end_col:
                    pre_text = line[:sel_start_col]
                    sel_text = line[sel_start_col:sel_end_col]
                    
                    pre_width = mono_font.size(pre_text)[0]
                    sel_width = mono_font.size(sel_text)[0]
                    
                    pygame.draw.rect(screen, (60, 80, 120), 
                                   (x_offset + pre_width, y, sel_width, self.line_height))
            
            # 绘制代码文本（逐字符以支持语法高亮）
            self._draw_code_line(screen, mono_font, line, x_offset, y)
            
            # 光标
            if i == self.cursor_line and not self.is_running:
                cursor_x = x_offset + mono_font.size(line[:self.cursor_col])[0]
                pygame.draw.line(screen, (200, 200, 200),
                               (cursor_x, y + 2), (cursor_x, y + self.line_height - 2), 2)

        # 滚动条
        total_lines = len(self.lines)
        if total_lines > self._visible_lines:
            sb_x = self.editor_x + self.editor_width - 6
            sb_h = self.editor_height
            thumb_h = max(20, int(sb_h * self._visible_lines / total_lines))
            max_scroll = max(1, (total_lines - self._visible_lines) * self.line_height)
            thumb_y = self.editor_y + int((sb_h - thumb_h) * self.scroll_y / max_scroll)
            pygame.draw.rect(screen, (60, 60, 70), (sb_x, self.editor_y, 6, sb_h))
            pygame.draw.rect(screen, (140, 140, 150), (sb_x, thumb_y, 6, thumb_h))

        # 边框
        pygame.draw.rect(screen, (100, 100, 100), (self.x, self.y, self.width, self.height), 2)
    
    def _draw_code_line(self, screen: pygame.Surface, font: pygame.font.Font, 
                        line: str, x: int, y: int):
        """绘制代码行（pygments 语法高亮）"""
        if _has_pygments:
            self._draw_highlighted_line(screen, font, line, x, y)
        else:
            self._draw_simple_line(screen, font, line, x, y)

    def _draw_highlighted_line(self, screen: pygame.Surface, font: pygame.font.Font,
                               line: str, x: int, y: int):
        """pygments 语法高亮渲染"""
        if not line:
            return
        try:
            tokens = list(lex(line, PythonLexer()))
            x_offset = x
            for ttype, text in tokens:
                text = text.replace('\r', '').replace('\n', '')
                if not text:
                    continue
                color = _token_color(ttype)
                surf = font.render(text, True, color)
                screen.blit(surf, (x_offset, y))
                x_offset += surf.get_width()
        except Exception:
            self._draw_simple_line(screen, font, line, x, y)

    def _draw_simple_line(self, screen: pygame.Surface, font: pygame.font.Font,
                          line: str, x: int, y: int):
        """简单语法高亮（无 pygments 时的后备方案）"""
        line = line.replace('\r', '')
        x_offset = x

        if line.strip().startswith('#'):
            surf = font.render(line, True, (100, 180, 100))
            screen.blit(surf, (x_offset, y))
            return

        keywords = {'def', 'class', 'import', 'from', 'if', 'elif', 'else', 'for',
                   'while', 'return', 'try', 'except', 'finally', 'with', 'as',
                   'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is',
                   'yield', 'raise', 'break', 'continue', 'pass', 'global', 'lambda'}

        token_pattern = re.compile(
            r'(?:^|\s)(#.*)'                  # 注释
            r'|("""[\s\S]*?""")'              # 三引号字符串
            r"|('''[\s\S]*?''')"              
            r'|("(?:[^"\\]|\\.)*")'           # 双引号字符串
            r"|('(?:[^'\\]|\\.)*')"           # 单引号字符串
            r'|\b(' + '|'.join(keywords) + r')\b'  # 关键字
            r'|(\b\d+\.?\d*\b)'               # 数字
            r'|(@\w+)'                        # 装饰器
        )

        pos = 0
        for m in token_pattern.finditer(line):
            if m.start() > pos:
                plain = line[pos:m.start()]
                surf = font.render(plain, True, (220, 220, 220))
                screen.blit(surf, (x_offset, y))
                x_offset += surf.get_width()

            match_text = m.group(0)
            if m.group(1):
                color = (100, 180, 100)
            elif m.group(2) or m.group(3) or m.group(4) or m.group(5):
                color = (220, 150, 100)
            elif m.group(6):
                color = (100, 150, 220)
            elif m.group(7):
                color = (180, 120, 220)
            elif m.group(8):
                color = (200, 180, 100)
            else:
                color = (220, 220, 220)

            surf = font.render(match_text, True, color)
            screen.blit(surf, (x_offset, y))
            x_offset += surf.get_width()
            pos = m.end()

        if pos < len(line):
            plain = line[pos:]
            surf = font.render(plain, True, (220, 220, 220))
            screen.blit(surf, (x_offset, y))
    
    def _draw_button(self, screen: pygame.Surface, font: pygame.font.Font,
                     btn_name: str, text: str, color):
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
