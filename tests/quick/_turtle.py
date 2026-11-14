"""标准库Turtle结束界面：显式发送后保持连接，关闭窗口才释放会话。"""
from _screen import connect_screen
from ai_robot.drawing import capture_turtle


class _Sender:
    def __init__(self, screen, connect_options=None, *, robot=None):
        import tkinter as tk
        self.screen = screen
        self.connect_options = dict(connect_options or {})
        if robot is not None and self.connect_options:
            raise ValueError('传入已有robot时不要再指定串口或屏幕IO，请在开头用robot.display.set配置')
        self._provided_robot = robot
        self._provided_released = False
        self.root = screen.getcanvas().winfo_toplevel()
        self.context = None
        self.robot = None
        self.busy = False
        self.closed = False
        self.status = tk.StringVar(value="绘图完成后点击发送；Enter也可发送。关闭窗口释放连接。")
        self.toolbar = tk.Frame(self.root)
        self.toolbar.pack(side="bottom", fill="x")
        self.button = tk.Button(self.toolbar, text="发送到 ESP32", command=self.send)
        self.button.pack(side="left", padx=8, pady=6)
        tk.Label(self.toolbar, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)
        self.root.bind("<Return>", self.send, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def release(self):
        context, self.context = self.context, None
        self.robot = None
        if context is not None:
            context.__exit__(None, None, None)
        if self._provided_robot is not None and not self._provided_released:
            self._provided_released = True
            self._provided_robot.close()

    def send(self, event=None):
        if self.busy or self.closed or self._provided_released:
            return
        self.busy = True
        self.button.configure(state="disabled")
        try:
            # Capture only the inner drawing area BEFORE opening USB or changing
            # board state. The toolbar/window border is never transmitted.
            image = capture_turtle(self.screen)
            try:
                if self.robot is None:
                    if self._provided_robot is not None:
                        self.robot = self._provided_robot
                        self.robot.start()
                    else:
                        context = connect_screen(**self.connect_options)
                        robot = context.__enter__()
                        self.context, self.robot = context, robot
                result = self.robot.display.image(image, fit="contain")
            finally:
                image.close()
            self.status.set(f"已发送 {result['width']}×{result['height']}，连接保持到窗口关闭；可继续绘图再发送。")
        except (Exception, SystemExit) as error:
            try:
                self.release()
            except (Exception, SystemExit):
                pass
            retry = '请关闭窗口，修正后重新运行程序。' if self._provided_robot is not None else '修正后再次点击发送。'
            self.status.set(f"发送失败：{error}；{retry}")
            from tkinter import messagebox
            messagebox.showerror("Turtle发送失败", str(error), parent=self.root)
        finally:
            self.busy = False
            if not self.closed:
                self.button.configure(state="disabled" if self._provided_released else "normal")

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.release()
        except (Exception, SystemExit) as error:
            print("关闭连接时无法确认输出清理：", error)
        finally:
            try:
                self.screen.bye()
            except Exception:
                pass


def finish(screen=None, *, robot=None, port=None, **display):
    """Add Send controls. Reuse robot=... or open one connection on first send.

    robot=existing_robot reuses that already-open connection; configure it with
    display.set() at the top of the file. The first Send calls robot.start().
    Closing the window closes that connection and stops its outputs, even when
    no image was sent. Do not also pass port or display IO in this mode.
    Without robot, port/IO are used only on Send, preserving the original mode.
    """
    if robot is not None and (port is not None or display):
        raise ValueError('已有robot与第二组连接参数不能混用；请在开头用robot.display.set配置')
    if screen is None:
        import turtle
        screen = turtle.Screen()
    options = dict(display)
    if port is not None:
        options['port'] = port
    sender = _Sender(screen, options, robot=robot) if robot is not None else _Sender(screen, options)
    try:
        screen.mainloop()
    finally:
        sender.close()
