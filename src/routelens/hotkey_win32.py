"""Windows 系统级全局热键（不依赖窗口焦点）。

面板鼠标穿透后收不到键盘焦点，Tk bind 全部失效；
Shift+S 切换穿透必须走 RegisterHotKey 才能在穿透状态下仍然生效。

实现：专用工作线程创建 message-only 隐藏窗口，RegisterHotKey 绑定该 HWND。
WM_HOTKEY 直接进入窗口过程，与线程消息队列的时序细节解耦。
注册/注销命令经 SendMessage 到窗口过程执行（天然同线程 + 同步返回结果）。
仅 Windows 可用；其他平台 available=False，调用方降级。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Any, Callable

WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
WM_APP_COMMAND = 0x8001  # WM_APP(0x8000) 起为应用私有
SMTO_NORMAL = 0x0000
HWND_MESSAGE = wintypes.HWND(-3)
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_S = 0x53

# 热键 ID（进程内唯一即可）
HOTKEY_TOGGLE_CLICK_THROUGH = 1

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,  # LRESULT（64 位必须 longlong）
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class WNDCLASSW(ctypes.Structure):
    """ctypes.wintypes 未提供 WNDCLASSW，自行定义。"""

    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _bind_user32(user32: Any) -> None:
    """声明 64 位指针参数/返回类型，避免默认 c_int 截断。"""
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,  # dwExStyle
        wintypes.LPCWSTR,  # lpClassName
        wintypes.LPCWSTR,  # lpWindowName
        wintypes.DWORD,  # dwStyle
        ctypes.c_int,  # x
        ctypes.c_int,  # y
        ctypes.c_int,  # nWidth
        ctypes.c_int,  # nHeight
        wintypes.HWND,  # hWndParent
        wintypes.HMENU,  # hMenu
        wintypes.HINSTANCE,  # hInstance
        wintypes.LPVOID,  # lpParam
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.SendMessageTimeoutW.restype = ctypes.c_longlong
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]


class GlobalHotkeys:
    """RegisterHotKey 封装：message-only 窗口 + 工作线程；回调经 schedule 抛回 UI 线程。"""

    def __init__(self, schedule: Callable[[Callable[[], None]], None]) -> None:
        self._schedule = schedule
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered: set[int] = set()
        self._lock = threading.Lock()
        self._hwnd: int = 0
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._pending: dict[int, dict[str, Any]] = {}
        self._cookie = 0
        self._wndproc_ref: WNDPROC | None = None
        # 最近一次 RegisterHotKey 失败的 GetLastError 码（0=无错）
        self.last_error: int = 0

    @property
    def available(self) -> bool:
        return hasattr(ctypes, "windll")

    # ---- 公开 API（UI 线程调用）----

    def set_callback(self, hotkey_id: int, callback: Callable[[], None] | None) -> None:
        with self._lock:
            if callback is None:
                self._callbacks.pop(hotkey_id, None)
            else:
                self._callbacks[hotkey_id] = callback

    def register(self, hotkey_id: int, fs_modifiers: int, vk_code: int) -> bool:
        """注册全局热键。返回是否成功（同步）。"""
        if not self.available:
            return False
        if not self._ensure_window():
            return False
        box = self._call(self._do_register, hotkey_id, fs_modifiers, vk_code)
        return bool(box.get("result", False))

    def unregister(self, hotkey_id: int) -> None:
        if not self.available or not self._hwnd:
            return
        self._call(self._do_unregister, hotkey_id)

    def shutdown(self) -> None:
        """销毁窗口并结束工作线程；幂等。"""
        hwnd = self._hwnd
        if hwnd:
            self._call(lambda: ctypes.windll.user32.DestroyWindow(hwnd))
            thread = self._thread
            if thread is not None:
                thread.join(timeout=2.0)
        self._thread = None
        self._hwnd = 0

    # ---- 内部：命令经 SendMessage 同步派发到窗口过程（工作线程执行）----

    def _call(self, fn: Callable[..., Any], *args: Any, timeout_ms: int = 2000) -> dict[str, Any]:
        with self._lock:
            self._cookie += 1
            cookie = self._cookie
            box: dict[str, Any] = {}
            self._pending[cookie] = (fn, args, box)
        sent = wintypes.DWORD(0)
        ok = ctypes.windll.user32.SendMessageTimeoutW(
            self._hwnd,
            WM_APP_COMMAND,
            wintypes.WPARAM(cookie),
            wintypes.LPARAM(0),
            SMTO_NORMAL,
            timeout_ms,
            ctypes.byref(sent),
        )
        if not ok:
            with self._lock:
                self._pending.pop(cookie, None)
            box["error"] = TimeoutError("hotkey window unreachable")
        return box

    def _do_register(self, hotkey_id: int, fs_modifiers: int, vk_code: int) -> bool:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if hotkey_id in self._registered:
            user32.UnregisterHotKey(self._hwnd, hotkey_id)
            self._registered.discard(hotkey_id)
        ok = bool(user32.RegisterHotKey(self._hwnd, hotkey_id, fs_modifiers, vk_code))
        self.last_error = 0 if ok else int(kernel32.GetLastError())
        if ok:
            self._registered.add(hotkey_id)
        return ok

    def _do_unregister(self, hotkey_id: int) -> None:
        if hotkey_id in self._registered:
            ctypes.windll.user32.UnregisterHotKey(self._hwnd, hotkey_id)
            self._registered.discard(hotkey_id)

    # ---- 工作线程：创建 message-only 窗口并泵消息 ----

    def _ensure_window(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._hwnd:
                return True
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._window_thread, name="routelens-hotkey", daemon=True
            )
            self._thread.start()
        self._ready.wait(timeout=5.0)
        return bool(self._hwnd)

    def _window_thread(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        _bind_user32(user32)
        try:
            self._wndproc_ref = WNDPROC(self._wndproc)
            # 每实例唯一类名：窗口类按进程注册，共享名会让第二个实例
            # 复用第一个实例的 wndproc → 消息进错对象、_call 永远拿不到结果
            class_name = f"RouteLensHotkeyWnd_{id(self):x}"
            wndclass = WNDCLASSW()
            wndclass.lpfnWndProc = self._wndproc_ref
            wndclass.lpszClassName = class_name
            wndclass.hInstance = kernel32.GetModuleHandleW(None)
            atom = user32.RegisterClassW(ctypes.byref(wndclass))
            if not atom:
                self._ready.set()
                return
            hwnd = user32.CreateWindowExW(
                0,
                class_name,
                None,
                0,
                0,
                0,
                0,
                0,
                HWND_MESSAGE,  # message-only 窗口：不可见、不进任务栏
                None,
                wndclass.hInstance,
                None,
            )
            if not hwnd:
                self._ready.set()
                return
            self._hwnd = int(hwnd)
        finally:
            self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_HOTKEY:
                with self._lock:
                    callback = self._callbacks.get(int(wparam))
                if callback is not None:
                    self._schedule(callback)
                return 0
            if msg == WM_APP_COMMAND:
                with self._lock:
                    item = self._pending.pop(int(wparam), None)
                if item is not None:
                    fn, args, box = item
                    try:
                        box["result"] = fn(*args)
                    except Exception as exc:  # noqa: BLE001 - 结果回传给调用方
                        box["error"] = exc
                return 0
            if msg == WM_DESTROY:
                ctypes.windll.user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return int(ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam))
