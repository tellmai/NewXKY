"""Windows wheel input limited to the user's selected question window.

No option/button clicks are sent. Restore the pointer unless the user moved it.
"""
import ctypes
import os
import sys
from ctypes import wintypes


class ScrollUnavailable(RuntimeError):
    pass


class RegionScroller:
    def __init__(self):
        self.root = None

    def reset(self):
        self.root = None

    @staticmethod
    def interrupted():
        return (sys.platform == 'win32'
                and bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000))

    def wheel(self, region, direction):
        if sys.platform != 'win32':
            raise ScrollUnavailable('当前系统不支持自动滚动，请手动滚动框选区域')
        from PySide6.QtCore import QPoint, QTimer
        from PySide6.QtGui import QCursor

        user = ctypes.WinDLL('user32', use_last_error=True)
        user.WindowFromPoint.argtypes = [wintypes.POINT]
        user.WindowFromPoint.restype = wintypes.HWND
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetForegroundWindow.restype = wintypes.HWND
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        point = QPoint(region.x() + region.width() * 3 // 4,
                       region.y() + region.height() // 2)
        original = QCursor.pos()
        QCursor.setPos(point)

        def restore():
            if QCursor.pos() == point:
                QCursor.setPos(original)

        try:
            physical = wintypes.POINT()
            if not user.GetCursorPos(ctypes.byref(physical)):
                raise ScrollUnavailable('无法定位框选区域的滚动位置')
            target = user.WindowFromPoint(physical)
            root = user.GetAncestor(target, 2) if target else None
            process = wintypes.DWORD()
            if root:
                user.GetWindowThreadProcessId(root, ctypes.byref(process))
            if not root or process.value == os.getpid():
                raise ScrollUnavailable('软件窗口遮挡了题目，请移到框选区域外')
            if self.root is not None and root != self.root:
                raise ScrollUnavailable('框选区域的窗口已变化，已停止自动滚动，请重新开始识别')
            self.root = root
            if user.GetForegroundWindow() != root:
                user.SetForegroundWindow(root)
                if user.GetForegroundWindow() != root:
                    raise ScrollUnavailable('无法滚动当前考试窗口，请激活考试页面后重试')
            if self.interrupted():
                raise ScrollUnavailable('已按 Esc 停止自动滚动')

            class MouseInput(ctypes.Structure):
                _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                            ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                            ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

            class Input(ctypes.Structure):
                _fields_ = [('type', wintypes.DWORD), ('mouse', MouseInput)]

            user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
            user.SendInput.restype = wintypes.UINT
            notches = max(1, min(3, region.height() // 300))
            # A real move packet updates wheel routing as well as the cursor's
            # position; SetCursorPos alone can leave native scroll views idle.
            left,top=user.GetSystemMetrics(76),user.GetSystemMetrics(77)
            width,height=user.GetSystemMetrics(78),user.GetSystemMetrics(79)
            x=round((physical.x-left)*65535/max(1,width-1))
            y=round((physical.y-top)*65535/max(1,height-1))
            events=(Input*2)(Input(0,MouseInput(x,y,0,0xC001,0,0)),
                             Input(0,MouseInput(0,0,(direction*notches*120)&0xFFFFFFFF,0x0800,0,0)))
            if user.SendInput(2, events, ctypes.sizeof(Input)) != 2:
                raise ScrollUnavailable('系统未接受滚动输入，请手动滚动或重新开始识别')
        except Exception:
            restore()
            raise
        # Leave time for Windows to route the wheel at the selected pane.
        QTimer.singleShot(60, restore)
