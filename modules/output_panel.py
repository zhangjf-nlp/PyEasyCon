"""
Output Panel Module - 运行输出面板模块
支持鼠标滚轮滚动和自动换行
"""

import pygame
from typing import List


class OutputPanel:
    """运行输出面板模块"""

    def __init__(self, x: int, y: int, width: int = 730, height: int = 330):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        self.logs: List[str] = []
        self.max_logs = 500

        # 内容显示区域
        self.content_x = x + 8
        self.content_y = y + 36
        self.content_width = width - 16
        self.content_height = height - 44

        # 滚动
        self.scroll_offset = 0        # 滚动偏移（像素）
        self.max_scroll = 0
        self.auto_scroll = True       # 新日志时自动滚到底；用户手动滚轮后置 False
        self.dragging_scrollbar = False
        self.scrollbar_rect = pygame.Rect(0, 0, 0, 0)

        # 换行 + 渲染缓存（只在日志变化时重建）
        self.wrapped_cache: List[tuple] = []  # [(text, color), ...]
        self.surface_cache: List[pygame.Surface] = []  # 预渲染 Surface
        self.cache_dirty = True

    def log(self, msg: str):
        import time
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {msg}")
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        self.cache_dirty = True
        print(f"[{timestamp}] {msg}")

    def clear(self):
        self.logs.clear()
        self.wrapped_cache.clear()
        self.surface_cache.clear()
        self.cache_dirty = True
        self.scroll_offset = 0
        self.max_scroll = 0

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """按像素宽度自动换行"""
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
                continue
            current = ""
            for ch in paragraph:
                test = current + ch
                if font.size(test)[0] <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = ch
            if current:
                lines.append(current)
        return lines

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理滚动事件，返回是否消费了事件"""
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            if event.button == 4:  # 滚轮上
                self.scroll_offset = max(0, self.scroll_offset - 36)
                self.auto_scroll = False
                return True
            elif event.button == 5:  # 滚轮下
                self.scroll_offset = min(self.max_scroll, self.scroll_offset + 36)
                if self.scroll_offset >= self.max_scroll:
                    self.auto_scroll = True  # 滚到底恢复自动滚动
                return True
            elif event.button == 1 and self.scrollbar_rect.collidepoint(mx, my):
                self.dragging_scrollbar = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_scrollbar = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_scrollbar:
                mx, my = pygame.mouse.get_pos()
                # 滚动条在槽内的位置
                scrollbar_h = self.scrollbar_rect.height
                track_h = self.content_height
                if track_h > 0 and scrollbar_h > 0:
                    ratio = (my - self.content_y - scrollbar_h // 2) / (track_h - scrollbar_h)
                    ratio = max(0, min(1, ratio))
                    self.scroll_offset = int(ratio * self.max_scroll)
                return True
        return False

    def rebuild_cache(self, small_font: pygame.font.Font):
        """换行 + 预渲染所有日志行（仅当日志变化时调用）"""
        self.wrapped_cache.clear()
        self.surface_cache.clear()

        default_color = (200, 200, 200)
        for log in self.logs:
            lower_log = log.lower()
            if "错误" in lower_log or "失败" in lower_log or "error" in lower_log:
                color = (255, 100, 100)
            elif "成功" in lower_log or "完成" in lower_log or "success" in lower_log:
                color = (100, 255, 100)
            elif "警告" in lower_log or "warning" in lower_log:
                color = (255, 200, 100)
            else:
                color = default_color

            wrapped_lines = self.wrap_text(log, small_font, self.content_width - 8)
            for line in wrapped_lines:
                self.wrapped_cache.append((line, color))
                self.surface_cache.append(small_font.render(line, True, color))
                if len(self.wrapped_cache) > 2000:
                    self.cache_dirty = False
                    return

        self.cache_dirty = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        bg = (25, 25, 30)
        title_bg = (35, 35, 40)
        content_bg = (20, 20, 25)
        border_color = (100, 100, 100)

        # 背景
        pygame.draw.rect(screen, bg, (self.x, self.y, self.width, self.height))

        # 标题栏
        pygame.draw.rect(screen, title_bg, (self.x, self.y, self.width, 30))
        title_surf = font.render("运行输出", True, (200, 200, 200))
        screen.blit(title_surf, (self.x + 10, self.y + 6))

        # 内容区域背景
        content_rect = pygame.Rect(self.content_x, self.content_y, self.content_width, self.content_height)
        pygame.draw.rect(screen, content_bg, content_rect)

        # 有变化时重建缓存
        if self.cache_dirty:
            self.rebuild_cache(small_font)

        line_height = small_font.get_height() + 2
        total_lines = len(self.surface_cache)
        self.max_scroll = max(0, total_lines * line_height - self.content_height)

        # 自动滚动：用户没有手动上滚时，始终显示最新
        if self.auto_scroll:
            self.scroll_offset = self.max_scroll

        start_idx = self.scroll_offset // line_height

        # 裁剪到内容区域
        screen.set_clip(content_rect)

        for i in range(start_idx, min(total_lines, start_idx + self.content_height // line_height + 2)):
            y = self.content_y + 4 + i * line_height - self.scroll_offset
            if y + line_height < self.content_y:
                continue
            if y > self.content_y + self.content_height:
                break
            screen.blit(self.surface_cache[i], (self.content_x + 4, y))

        screen.set_clip(None)

        # 滚动条
        if self.max_scroll > 0:
            bar_width = 6
            track_x = self.x + self.width - bar_width - 3
            track_y = self.content_y
            track_h = self.content_height
            pygame.draw.rect(screen, (50, 50, 55), (track_x, track_y, bar_width, track_h), border_radius=3)

            visible_ratio = min(1.0, self.content_height / max(1, total_lines * line_height))
            bar_h = max(20, int(track_h * visible_ratio))
            bar_y = track_y + int((track_h - bar_h) * (self.scroll_offset / max(1, self.max_scroll)))
            self.scrollbar_rect = pygame.Rect(track_x, bar_y, bar_width, bar_h)

            bar_color = (140, 140, 150) if self.dragging_scrollbar else (100, 100, 110)
            pygame.draw.rect(screen, bar_color, self.scrollbar_rect, border_radius=3)

        # 边框
        pygame.draw.rect(screen, border_color, (self.x, self.y, self.width, self.height), 2)

    def get_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)