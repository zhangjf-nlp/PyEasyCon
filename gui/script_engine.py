import threading
import ctypes
import time
from typing import Optional, Callable


class ScriptEngine:
    def __init__(self, log_func: Callable[[str], None]):
        self.log_cb = log_func
        self.script_running = False
        self.stop_event = threading.Event()
        self.script_thread: Optional[threading.Thread] = None
        self.script_func: Optional[Callable] = None
        self.code_getter: Optional[Callable[[], str]] = None
        self.on_running_change: Optional[Callable[[bool], None]] = None

    def set_script_func(self, func: Callable):
        self.script_func = func

    def set_code_getter(self, getter: Callable[[], str]):
        self.code_getter = getter

    def set_on_running_change(self, callback: Callable[[bool], None]):
        self.on_running_change = callback

    def run(self, ctx, exec_globals_extra: dict = None):
        if self.script_running:
            self.log_cb("脚本已在运行中")
            return

        self.script_running = True
        self.stop_event.clear()

        if self.on_running_change:
            self.on_running_change(True)

        def script_worker():
            try:
                self.log_cb("=" * 40)
                self.log_cb("脚本开始运行")

                if self.script_func is not None:
                    self.script_func(ctx)
                elif self.code_getter is not None:
                    code = self.code_getter()
                    exec_globals = {
                        "ctx": ctx,
                        "is_running": lambda: not self.stop_event.is_set() and self.script_running,
                    }
                    if exec_globals_extra:
                        exec_globals.update(exec_globals_extra)
                    exec(code, exec_globals)
                else:
                    self.log_cb("没有可执行的脚本")

                self.log_cb("脚本运行完成")
            except SystemExit as e:
                self.log_cb(f"{e}")
            except Exception as e:
                self.log_cb(f"脚本错误: {e}")
                import traceback
                self.log_cb(traceback.format_exc())
            finally:
                self.script_running = False
                if self.on_running_change:
                    self.on_running_change(False)
                self.log_cb("=" * 40)

        self.script_thread = threading.Thread(target=script_worker, daemon=True)
        self.script_thread.start()

    def stop(self):
        self.script_running = False
        self.stop_event.set()
        self.log_cb("正在停止脚本...")

        if self.script_thread and self.script_thread.is_alive():
            try:
                tid = self.script_thread.ident
                if tid:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(tid),
                        ctypes.py_object(SystemExit)
                    )
                time.sleep(0.1)
                if self.script_thread.is_alive():
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(tid),
                        ctypes.py_object(SystemExit)
                    )
                    time.sleep(0.2)
            except Exception as e:
                self.log_cb(f"停止线程时出错: {e}")

        self.stop_event.clear()
        if self.on_running_change:
            self.on_running_change(False)
        self.log_cb("脚本已停止")

    def is_running(self) -> bool:
        return self.script_running and not self.stop_event.is_set()