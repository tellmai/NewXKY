"""Windows input scoped to one explicitly selected browser window."""
import ctypes
import sys
from ctypes import wintypes


ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
MARKER = 0x4E584B59


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",wintypes.LONG),("dy",wintypes.LONG),("mouseData",wintypes.DWORD),
                ("dwFlags",wintypes.DWORD),("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",wintypes.WORD),("wScan",wintypes.WORD),("dwFlags",wintypes.DWORD),
                ("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg",wintypes.DWORD),("wParamL",wintypes.WORD),("wParamH",wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi",MOUSEINPUT),("ki",KEYBDINPUT),("hi",HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type",wintypes.DWORD),("u",INPUTUNION)]


class MOUSEHOOK(ctypes.Structure):
    _fields_ = [("pt",wintypes.POINT),("mouseData",wintypes.DWORD),("flags",wintypes.DWORD),
                ("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]


class KEYHOOK(ctypes.Structure):
    _fields_ = [("vkCode",wintypes.DWORD),("scanCode",wintypes.DWORD),("flags",wintypes.DWORD),
                ("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize",wintypes.DWORD),("rcMonitor",wintypes.RECT),
                ("rcWork",wintypes.RECT),("dwFlags",wintypes.DWORD)]


def pixel_to_logical(point, origin, ratio):
    if ratio <= 0:
        raise ValueError("截图缩放比例无效")
    return origin[0]+point[0]/ratio,origin[1]+point[1]/ratio


class GlobalEscape:
    """Only Esc is reserved in DOM mode; other mouse/keyboard input is free."""
    def __init__(self,callback):
        from PySide6.QtCore import QAbstractNativeEventFilter
        from PySide6.QtWidgets import QApplication
        self.app=QApplication.instance()
        self.user=ctypes.WinDLL("user32",use_last_error=True)
        self.key=0x584B
        self.registered=False
        class Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self,event_type,message):
                try:
                    msg=wintypes.MSG.from_address(int(message))
                    if msg.message==0x0312 and msg.wParam==0x584B:
                        callback("已按 Esc 暂停自动答题，可从当前题继续")
                except (ValueError,TypeError):
                    pass
                return False,0
        self.filter=Filter()
        if self.user.RegisterHotKey(None,self.key,0x4000,0x1B):
            self.registered=True
            self.app.installNativeEventFilter(self.filter)

    def close(self):
        if self.registered:
            self.user.UnregisterHotKey(None,self.key)
            self.app.removeNativeEventFilter(self.filter)
            self.registered=False


class DesktopInput:
    def __init__(self,region,screen,on_interrupt):
        if sys.platform != "win32":
            raise RuntimeError("自动答题目前支持 Windows")
        self.user = ctypes.WinDLL("user32",use_last_error=True)
        self.region = region
        self.screen = screen
        self.screen_geometry = screen.geometry()
        self.screen_ratio = screen.devicePixelRatio()
        self.on_interrupt = on_interrupt
        self.interrupted = False
        self.hwnd = None
        self.hooks = []
        self.callbacks = []
        u = self.user
        u.GetAncestor.argtypes = (wintypes.HWND,wintypes.UINT)
        u.GetAncestor.restype = wintypes.HWND
        u.GetForegroundWindow.restype = wintypes.HWND
        u.WindowFromPoint.argtypes = (wintypes.POINT,)
        u.WindowFromPoint.restype = wintypes.HWND
        u.GetWindowRect.argtypes = (wintypes.HWND,ctypes.POINTER(wintypes.RECT))
        u.IsWindowVisible.argtypes = u.IsIconic.argtypes = (wintypes.HWND,)
        u.GetClassNameW.argtypes = (wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
        u.SetForegroundWindow.argtypes = (wintypes.HWND,)
        u.SendInput.argtypes = (wintypes.UINT,ctypes.POINTER(INPUT),ctypes.c_int)
        u.SendInput.restype = wintypes.UINT
        u.MonitorFromPoint.argtypes = (wintypes.POINT,wintypes.DWORD)
        u.MonitorFromPoint.restype = wintypes.HMONITOR
        u.GetMonitorInfoW.argtypes = (wintypes.HMONITOR,ctypes.POINTER(MONITORINFO))
        u.CallNextHookEx.argtypes = (wintypes.HHOOK,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        u.CallNextHookEx.restype = LRESULT
        u.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
        self._hook_type = ctypes.WINFUNCTYPE(LRESULT,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        u.SetWindowsHookExW.argtypes = (ctypes.c_int,self._hook_type,wintypes.HINSTANCE,wintypes.DWORD)
        u.SetWindowsHookExW.restype = wintypes.HHOOK
        # Get the physical origin of this Qt screen without multiplying global
        # desktop coordinates (which is wrong on mixed-scale monitor layouts).
        from PySide6.QtGui import QCursor
        previous = QCursor.pos()
        # GetCursorPos and Qt's current screen-independent cursor position give
        # a physical point on a known monitor without moving the user's cursor.
        physical = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(physical))
        from PySide6.QtGui import QGuiApplication
        cursor_screen = QGuiApplication.screenAt(previous)
        monitor = u.MonitorFromPoint(physical,2)
        info = MONITORINFO(ctypes.sizeof(MONITORINFO))
        if not u.GetMonitorInfoW(monitor,ctypes.byref(info)) or cursor_screen is None:
            raise RuntimeError("无法读取显示器坐标")
        # Enumerate monitors to identify the selected Qt screen, including when
        # the cursor currently lives on another screen.
        physical_rects = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HMONITOR,wintypes.HDC,
                                          ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
        def collect(handle,hdc,rect,data):
            device = ctypes.create_unicode_buffer(32)
            class MONITORINFOEX(ctypes.Structure):
                _fields_ = MONITORINFO._fields_+[("szDevice",wintypes.WCHAR*32)]
            details = MONITORINFOEX(ctypes.sizeof(MONITORINFOEX))
            if u.GetMonitorInfoW(handle,ctypes.cast(ctypes.byref(details),ctypes.POINTER(MONITORINFO))):
                physical_rects.append((details.szDevice,details.rcMonitor.left,details.rcMonitor.top,
                                       details.rcMonitor.right,details.rcMonitor.bottom))
            return True
        callback = callback_type(collect)
        u.EnumDisplayMonitors.argtypes = (wintypes.HDC,ctypes.POINTER(wintypes.RECT),callback_type,wintypes.LPARAM)
        if not u.EnumDisplayMonitors(None,None,callback,0):
            raise RuntimeError("无法枚举显示器")
        matching = [r for r in physical_rects if r[0].lower() == screen.name().lower()]
        if not matching:
            g,ratio = self.screen_geometry,self.screen_ratio
            # Qt 6 may expose an EDID friendly name rather than DISPLAY1.
            # On Windows it keeps physical screen origins and scales sizes.
            matching = [r for r in physical_rects if r[1:3] == (g.x(),g.y())
                        and abs(r[3]-r[1]-g.width()*ratio) <= 3
                        and abs(r[4]-r[2]-g.height()*ratio) <= 3]
        if len(matching) != 1:
            raise RuntimeError("无法对应所选显示器，请重新框选")
        _,left,top,right,bottom = matching[0]
        self.physical_origin = (left,top)
        self.physical_scale = ((right-left)/self.screen_geometry.width(),
                               (bottom-top)/self.screen_geometry.height())

    def _native(self,point):
        g = self.screen_geometry
        return wintypes.POINT(round(self.physical_origin[0]+(point[0]-g.x())*self.physical_scale[0]),
                              round(self.physical_origin[1]+(point[1]-g.y())*self.physical_scale[1]))

    def _logical_rect(self,rect):
        from PySide6.QtCore import QRect
        g = self.screen_geometry
        x = g.x()+(rect[0]-self.physical_origin[0])/self.physical_scale[0]
        y = g.y()+(rect[1]-self.physical_origin[1])/self.physical_scale[1]
        return QRect(round(x),round(y),round((rect[2]-rect[0])/self.physical_scale[0]),
                     round((rect[3]-rect[1])/self.physical_scale[1]))

    def _root(self,hwnd):
        return self.user.GetAncestor(hwnd,3) if hwnd else None  # GA_ROOTOWNER

    def _bounds(self,hwnd):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd,ctypes.byref(rect)):
            raise RuntimeError("浏览器窗口已关闭")
        return rect.left,rect.top,rect.right,rect.bottom

    def bind(self):
        center = self.region.center()
        target = self.user.WindowFromPoint(self._native((center.x(),center.y())))
        self.hwnd = self._root(target)
        name = ctypes.create_unicode_buffer(256)
        self.user.GetClassNameW(self.hwnd,name,len(name))
        if not (name.value.startswith("Chrome_WidgetWin") or name.value in {"MozillaWindowClass","IEFrame"}):
            raise RuntimeError("框选区域不在可见的浏览器窗口内，请调整浏览器后重试")
        self.bounds = self._bounds(self.hwnd)
        if not self._logical_rect(self.bounds).contains(self.region):
            raise RuntimeError("框选区域超出浏览器窗口，请重新框选")
        self.user.SetForegroundWindow(self.hwnd)
        self.validate()
        self._install_hooks()

    def _interrupt(self,reason):
        if not self.interrupted:
            self.interrupted = True
            self.on_interrupt(reason)

    def _install_hooks(self):
        kernel = ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel.GetModuleHandleW.restype = wintypes.HINSTANCE
        module = kernel.GetModuleHandleW(None)
        def mouse(code,kind,data):
            if code >= 0 and kind in {0x201,0x204,0x207,0x20A,0x20E}:
                event = ctypes.cast(data,ctypes.POINTER(MOUSEHOOK)).contents
                if not event.flags & 1 and event.dwExtraInfo != MARKER:
                    self._interrupt("检测到手动鼠标操作，自动答题已停止")
            return self.user.CallNextHookEx(None,code,kind,data)
        def keyboard(code,kind,data):
            if code >= 0 and kind in {0x100,0x104}:
                event = ctypes.cast(data,ctypes.POINTER(KEYHOOK)).contents
                if not event.flags & 0x10 and event.dwExtraInfo != MARKER:
                    self._interrupt("已按 Esc 停止自动答题" if event.vkCode==0x1B else "检测到手动键盘操作，自动答题已停止")
            return self.user.CallNextHookEx(None,code,kind,data)
        try:
            for hook_id,function in ((14,mouse),(13,keyboard)):
                callback = self._hook_type(function)
                hook = self.user.SetWindowsHookExW(hook_id,callback,module,0)
                if not hook:
                    raise RuntimeError("无法注册全局停止按键，未启动自动答题")
                self.callbacks.append(callback)
                self.hooks.append(hook)
        except Exception:
            self.close()
            raise

    def validate(self,*,whole_window=False):
        if self.interrupted:
            raise RuntimeError("自动答题已被手动停止")
        if self.screen.geometry() != self.screen_geometry or self.screen.devicePixelRatio() != self.screen_ratio:
            raise RuntimeError("显示器布局或缩放变化，请重新框选")
        if not self.user.IsWindowVisible(self.hwnd) or self.user.IsIconic(self.hwnd):
            raise RuntimeError("浏览器不可见，自动答题已停止")
        if self._bounds(self.hwnd) != self.bounds:
            raise RuntimeError("浏览器窗口位置变化，自动答题已停止")
        if self._root(self.user.GetForegroundWindow()) != self.hwnd:
            raise RuntimeError("浏览器失去焦点，自动答题已停止")
        r = self.region
        # Check coverage as well as focus: an always-on-top window can cover a
        # foreground browser. Individual click points are checked again later.
        if not whole_window:
            for x,y in ((r.x()+8,r.y()+8),(r.right()-8,r.y()+8),
                        (r.x()+8,r.bottom()-8),(r.right()-8,r.bottom()-8),
                        (r.center().x(),r.center().y())):
                if self._root(self.user.WindowFromPoint(self._native((x,y)))) != self.hwnd:
                    raise RuntimeError("识别区域被其他窗口遮挡，自动答题已停止")

    def capture_rect(self,whole_window=False):
        self.validate(whole_window=whole_window)
        if not whole_window:
            return self.region
        rect = self._logical_rect(self.bounds)
        foreground = self.user.GetForegroundWindow()
        if foreground != self.hwnd and self._root(foreground) == self.hwnd:
            rect = rect.united(self._logical_rect(self._bounds(foreground)))
        return rect.intersected(self.screen_geometry)

    def perform(self,action,origin,ratio,*,whole_window=False):
        self.validate(whole_window=whole_window)
        x,y = pixel_to_logical(action.point,origin,ratio)
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QCursor
        if not self.screen_geometry.contains(QPoint(round(x),round(y))):
            raise RuntimeError("点击位置超出所选显示器")
        if not whole_window and not self.region.contains(QPoint(round(x),round(y))):
            raise RuntimeError("点击位置超出框选区域")
        QCursor.setPos(self.screen,QPoint(round(x),round(y)))
        point = wintypes.POINT()
        self.user.GetCursorPos(ctypes.byref(point))
        if self._root(self.user.WindowFromPoint(point)) != self.hwnd:
            raise RuntimeError("目标位置被其他窗口遮挡，已取消点击")
        if action.kind == "click":
            events = (INPUT*2)()
            events[0].type = events[1].type = 0
            events[0].mi = MOUSEINPUT(0,0,0,0x0002,0,MARKER)
            events[1].mi = MOUSEINPUT(0,0,0,0x0004,0,MARKER)
        else:
            events = (INPUT*1)()
            events[0].type = 0
            events[0].mi = MOUSEINPUT(0,0,action.amount & 0xFFFFFFFF,0x0800,0,MARKER)
        inserted = self.user.SendInput(len(events),events,ctypes.sizeof(INPUT))
        if inserted != len(events):
            # Ensure a partially delivered pair never leaves the mouse held.
            if action.kind == "click":
                release = INPUT(type=0)
                release.mi = MOUSEINPUT(0,0,0,0x0004,0,MARKER)
                self.user.SendInput(1,ctypes.byref(release),ctypes.sizeof(INPUT))
            raise RuntimeError("Windows 未接受完整输入，自动答题已停止；请检查浏览器与程序权限是否一致")

    def close(self):
        for hook in self.hooks:
            self.user.UnhookWindowsHookEx(hook)
        self.hooks.clear()
        self.callbacks.clear()
