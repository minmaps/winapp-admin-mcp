"""Window ownership, process identity and integrity checked through Windows APIs."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

import win32api
import win32con
import win32gui
import win32process
import win32security

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.ProcessIdToSessionId.restype = wintypes.BOOL


@contextmanager
def managed_handle(handle):
    try:
        yield handle
    finally:
        handle.Close()


def session_id(pid: int) -> int:
    result = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(pid, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    return result.value


def canonical(path: str) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=True)))


def process_info(handle, pid: int) -> dict:
    buf = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(buf))
    if not kernel32.QueryFullProcessImageNameW(int(handle), 0, buf, ctypes.byref(length)):
        raise ctypes.WinError(ctypes.get_last_error())
    with managed_handle(win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)) as token:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        integrity_sid = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)[0]
        rid = integrity_sid.GetSubAuthority(integrity_sid.GetSubAuthorityCount() - 1)
        elevated = bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
    return {
        "pid": pid, "executable": buf.value,
        "created": str(win32process.GetProcessTimes(handle)["CreationTime"]),
        "user_sid": win32security.ConvertSidToStringSid(sid),
        "session_id": session_id(pid), "elevated": elevated,
        "integrity_rid": rid,
        "integrity": "system" if rid >= 16384 else "high" if rid >= 12288 else "medium" if rid >= 8192 else "low",
    }


def current_info() -> dict:
    with managed_handle(win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, os.getpid())) as handle:
        return process_info(handle, os.getpid())


@contextmanager
def window_info(hwnd: int):
    if not win32gui.IsWindow(hwnd) or win32gui.GetAncestor(hwnd, 2) != hwnd:
        raise ValueError("La fenêtre n'est plus une fenêtre principale valide; refaire list_windows.")
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    with managed_handle(win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)) as handle:
        info = process_info(handle, pid)
        if win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
            raise ValueError("La fenêtre a changé de propriétaire; refaire list_windows.")
        info.update(hwnd=hwnd, title=win32gui.GetWindowText(hwnd), class_name=win32gui.GetClassName(hwnd))
        yield info  # Keep the process handle open while WinApp is running.


def enumerate_windows() -> list[int]:
    found = []
    def collect(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            found.append(hwnd)
    win32gui.EnumWindows(collect, None)
    return found
