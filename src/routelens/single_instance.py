"""单实例守卫 + 唤醒已运行实例。

为什么需要：Shift+S 是 RegisterHotKey 系统级热键，同一时刻只能被一个进程持有。
「最小化到托盘」会把窗口 withdraw 但不退出进程，用户再点一次 exe 就会出现
第二个实例 —— 它注册 Shift+S 失败（WinError 1409），热键表现为「失效」。
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

_MUTEX_NAME = "Local\\RouteLens.SingleInstance"
_ACTIVATE_EVENT_NAME = "Local\\RouteLens.Activate"

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_SW_SHOW = 5
_SW_RESTORE = 9

# 进程存活期间必须一直持有，句柄关闭 = 守卫失效
_held_handles: list[int] = []


def _kernel32():
    return ctypes.windll.kernel32


def _user32():
    return ctypes.windll.user32


def acquire_single_instance() -> bool:
    """抢占单实例互斥体。True = 本进程是唯一实例；False = 已有实例在跑。"""
    if not hasattr(ctypes, "windll"):
        return True
    kernel32 = _kernel32()
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        # 守卫本身建不起来时放行：宁可多开，也不要打不开程序
        return True
    if int(kernel32.GetLastError()) == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _held_handles.append(int(handle))
    return True


def create_activation_event() -> int:
    """创建自动重置的唤醒事件（本实例接收「请显示窗口」请求）。"""
    if not hasattr(ctypes, "windll"):
        return 0
    kernel32 = _kernel32()
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    handle = kernel32.CreateEventW(None, False, False, _ACTIVATE_EVENT_NAME)
    if not handle:
        return 0
    _held_handles.append(int(handle))
    return int(handle)


def signal_existing_instance() -> bool:
    """唤起已运行实例（把收进托盘的窗口拿回来）。"""
    if not hasattr(ctypes, "windll"):
        return False
    kernel32 = _kernel32()
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, _ACTIVATE_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def activate_window_fallback() -> bool:
    """老版本实例没有唤醒事件时的兜底：直接显示它的 Tk 顶层窗口。"""
    if not hasattr(ctypes, "windll"):
        return False
    user32 = _user32()
    found: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _visit(hwnd, _lparam) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "RouteLens" not in title and "轨镜" not in title:
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "TkTopLevel":
            found.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc(_visit), 0)
    if not found:
        return False
    hwnd = found[0]
    user32.ShowWindow(hwnd, _SW_RESTORE if user32.IsIconic(hwnd) else _SW_SHOW)
    user32.SetForegroundWindow(hwnd)
    return True


def start_activation_watcher(event_handle: int, on_activate: Callable[[], None]) -> None:
    """后台线程等唤醒信号。on_activate 在工作线程执行，调用方负责切回 UI 线程。"""
    if not event_handle or not hasattr(ctypes, "windll"):
        return
    kernel32 = _kernel32()

    def _loop() -> None:
        while True:
            try:
                rc = kernel32.WaitForSingleObject(wintypes.HANDLE(event_handle), 1000)
            except Exception:  # noqa: BLE001 - 句柄失效即退出线程
                return
            if rc == _WAIT_OBJECT_0:
                try:
                    on_activate()
                except Exception:  # noqa: BLE001 - 回调异常不拖垮线程
                    pass

    threading.Thread(target=_loop, name="routelens-activate", daemon=True).start()
