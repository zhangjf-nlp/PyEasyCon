"""
Output Panel Module - 运行输出面板模块
显示日志和运行输出
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
        
        # 日志列表
        self.logs: List[str] = []
        self.max_logs = 100
        
        # 显示区域
        self.content_x = x + 10
        self.content_y = y + 40
        self.content_width = width - 20
        self.content_height = height - 50
    
    def log(self, msg: str):
        """添加日志"""
        import time
        timestamp = time.strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        self.logs.append(log_msg)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        print(log_msg)
    
    def clear(self):
        """清空日志"""
        self.logs.clear()
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        """绘制输出面板"""
        # 背景
        pygame.draw.rect(screen, (25, 25, 30), (self.x, self.y, self.width, self.height))
        
        # 标题栏
        pygame.draw.rect(screen, (35, 35, 40), (self.x, self.y, self.width, 35))
        
        # 标题
        title = font.render("运行输出", True, (200, 200, 200))
        screen.blit(title, (self.x + 10, self.y + 8))
        
        # 日志内容区域背景
        pygame.draw.rect(screen, (20, 20, 25),
                        (self.content_x, self.content_y, self.content_width, self.content_height))
        
        # 日志内容
        line_height = 18
        visible_logs = self.logs[-int(self.content_height / line_height):]
        
        for i, log in enumerate(visible_logs):
            y = self.content_y + 5 + i * line_height
            if y > self.y + self.height - 20:
                break
            
            # 根据内容类型设置颜色
            lower_log = log.lower()
            if "错误" in lower_log or "失败" in lower_log or "error" in lower_log:
                color = (255, 100, 100)
            elif "成功" in lower_log or "完成" in lower_log or "success" in lower_log:
                color = (100, 255, 100)
            elif "警告" in lower_log or "warning" in lower_log:
                color = (255, 200, 100)
            else:
                color = (200, 200, 200)
            
            surf = small_font.render(log, True, color)
            screen.blit(surf, (self.content_x + 5, y))
        
        # 边框
        pygame.draw.rect(screen, (100, 100, 100), (self.x, self.y, self.width, self.height), 2)
    
    def get_rect(self) -> pygame.Rect:
        """获取区域矩形"""
        return pygame.Rect(self.x, self.y, self.width, self.height)
