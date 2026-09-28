from __future__ import annotations

import argparse
import configparser
import ctypes
import json
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


MAX_TEXT_CHARS = 1024
ICON_SIZE = 48

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002

LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMPOSITION = LVM_FIRST + 16
LVM_SETITEMPOSITION32 = LVM_FIRST + 49
LVM_GETITEMSPACING = LVM_FIRST + 51
LVM_GETEXTENDEDLISTVIEWSTYLE = LVM_FIRST + 55
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVS_AUTOARRANGE = 0x0100
LVS_EX_SNAPTOGRID = 0x00080000
GWL_STYLE = -16

SHGFI_PIDL = 0x000008
SHGFI_SYSICONINDEX = 0x004000
SHCONTF_FOLDERS = 0x0020
SHCONTF_NONFOLDERS = 0x0040
SHCONTF_INCLUDEHIDDEN = 0x0080
SHGDN_NORMAL = 0x0000
SHGDN_FORPARSING = 0x8000
SHIL_EXTRALARGE = 2
ILD_TRANSPARENT = 0x0001
DI_NORMAL = 0x0003
MONITOR_DEFAULTTOPRIMARY = 1
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
STD_OUTPUT_HANDLE = -11
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

BACKUP_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ChromaticSorter"

MIN_SATURATION = 64
MIN_VALUE = 51
MIN_COLOURFUL_FRACTION = 0.15
HUE_START_OFFSET = 15

HUE_FAMILIES = (
    (15, "Red"), (40, "Orange"), (70, "Yellow"), (160, "Green"),
    (200, "Cyan"), (255, "Blue"), (290, "Purple"), (345, "Magenta"), (360, "Red"),
)

DEFAULT_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Gaming": (
        "steam", "steamapps", "steamlibrary", "epic games", "riot", "riot games", "battle.net",
        "ubisoft", "uplay", "gog", "gog galaxy", "xbox", "ea app", "origin", "rockstar games",
        "minecraft", "itch", "amazon games", "games", "game", "launcher",
    ),
    "Productivity": (
        "office", "microsoft 365", "word", "excel", "powerpoint", "outlook", "onenote",
        "libreoffice", "adobe", "acrobat", "photoshop", "lightroom", "illustrator", "premiere",
        "affinity", "gimp", "krita", "blender", "obsidian", "notion", "evernote",
        "audacity", "reaper", "handbrake", "davinci", "resolve",
    ),
    "Development": (
        "visual studio", "vs code", "code.exe", "jetbrains", "pycharm", "intellij", "webstorm",
        "rider", "clion", "android studio", "unity", "unity hub", "unreal", "godot", "docker",
        "git", "github", "arduino", "virtualbox", "vmware", "python", "node", "postman",
    ),
    "Utilities": (
        "discord", "slack", "zoom", "teams", "telegram", "whatsapp", "spotify", "stremio",
        "vlc", "chrome", "firefox", "brave", "opera", "edge", "vpn", "tunnelbear", "nvidia",
        "amd", "everything", "windirstat", "7-zip", "winrar", "obs", "splitcam", "fxsound",
        "recycle bin", "this pc", "control panel", "network",
    ),
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", ctypes.c_uint32),
        ("iItem", ctypes.c_int32),
        ("iSubItem", ctypes.c_int32),
        ("state", ctypes.c_uint32),
        ("stateMask", ctypes.c_uint32),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", ctypes.c_int32),
        ("iImage", ctypes.c_int32),
        ("lParam", ctypes.c_ssize_t),
        ("iIndent", ctypes.c_int32),
        ("iGroupId", ctypes.c_int32),
        ("cColumns", ctypes.c_uint32),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", ctypes.c_int32),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 1)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


IID_IImageList = GUID(0x46EB5926, 0x582E, 0x4017, (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class ColorProfile:
    hue: float | None
    saturation: float
    value: float
    rgb: tuple[int, int, int]

    @property
    def family(self) -> str:
        if self.hue is None:
            return "Neutral"
        return next(name for limit, name in HUE_FAMILIES if self.hue < limit)


@dataclass
class DesktopItem:
    index: int
    name: str
    position: Point
    source: str | None
    target: str | None
    category: str
    color: ColorProfile | None


@dataclass(frozen=True)
class ShellEntry:
    label: str
    parse_name: str
    icon_index: int
    target: str | None
    search_text: str

    @property
    def is_file(self) -> bool:
        return not self.parse_name.startswith("::")


@dataclass(frozen=True)
class Grid:
    origin: Point
    cell_width: int
    cell_height: int
    columns: int
    rows: int

    @property
    def capacity(self) -> int:
        return self.columns * self.rows

    def point(self, cell: tuple[int, int]) -> Point:
        column, row = cell
        return Point(self.origin.x + column * self.cell_width, self.origin.y + row * self.cell_height)


Cell = tuple[int, int]


def enable_dpi_awareness() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_int
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            return
    except AttributeError:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


class Win32Api:
    def __init__(self) -> None:
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self._declare_signatures()

    def _declare_signatures(self) -> None:
        handle = ctypes.c_void_p
        size = ctypes.c_size_t
        k, u, g = self.kernel32, self.user32, self.gdi32

        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.OpenProcess.restype = handle
        k.CloseHandle.argtypes = [handle]
        k.CloseHandle.restype = ctypes.c_int
        k.IsWow64Process.argtypes = [handle, ctypes.POINTER(ctypes.c_int)]
        k.IsWow64Process.restype = ctypes.c_int
        k.VirtualAllocEx.argtypes = [handle, handle, size, ctypes.c_uint32, ctypes.c_uint32]
        k.VirtualAllocEx.restype = handle
        k.VirtualFreeEx.argtypes = [handle, handle, size, ctypes.c_uint32]
        k.VirtualFreeEx.restype = ctypes.c_int
        k.ReadProcessMemory.argtypes = [handle, handle, handle, size, ctypes.POINTER(size)]
        k.ReadProcessMemory.restype = ctypes.c_int
        k.WriteProcessMemory.argtypes = [handle, handle, handle, size, ctypes.POINTER(size)]
        k.WriteProcessMemory.restype = ctypes.c_int
        k.GetStdHandle.argtypes = [ctypes.c_uint32]
        k.GetStdHandle.restype = handle
        k.GetConsoleMode.argtypes = [handle, ctypes.POINTER(ctypes.c_uint32)]
        k.GetConsoleMode.restype = ctypes.c_int
        k.SetConsoleMode.argtypes = [handle, ctypes.c_uint32]
        k.SetConsoleMode.restype = ctypes.c_int

        u.SendMessageTimeoutW.argtypes = [
            handle, ctypes.c_uint, size, ctypes.c_ssize_t, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(size),
        ]
        u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        u.DrawIconEx.argtypes = [
            handle, ctypes.c_int, ctypes.c_int, handle, ctypes.c_int, ctypes.c_int, ctypes.c_uint, handle, ctypes.c_uint,
        ]
        u.DrawIconEx.restype = ctypes.c_int
        u.DestroyIcon.argtypes = [handle]
        u.DestroyIcon.restype = ctypes.c_int

        g.CreateCompatibleDC.argtypes = [handle]
        g.CreateCompatibleDC.restype = handle
        g.DeleteDC.argtypes = [handle]
        g.DeleteDC.restype = ctypes.c_int
        g.SelectObject.argtypes = [handle, handle]
        g.SelectObject.restype = handle
        g.CreateDIBSection.argtypes = [
            handle, ctypes.POINTER(BITMAPINFO), ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), handle, ctypes.c_uint32,
        ]
        g.CreateDIBSection.restype = handle
        g.DeleteObject.argtypes = [handle]
        g.DeleteObject.restype = ctypes.c_int

        self.shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        self.shell32.SHGetImageList.restype = ctypes.c_long

    @staticmethod
    def raise_last_error(action: str) -> None:
        error = ctypes.get_last_error()
        raise OSError(error, f"{action}: {ctypes.FormatError(error).strip()}")

    def send_timeout(self, hwnd: int, message: int, wparam: int, lparam: int, timeout_ms: int = 2000) -> int:
        result = ctypes.c_size_t()
        succeeded = self.user32.SendMessageTimeoutW(
            ctypes.c_void_p(hwnd),
            message,
            ctypes.c_size_t(wparam),
            ctypes.c_ssize_t(lparam),
            SMTO_ABORTIFHUNG | SMTO_BLOCK,
            timeout_ms,
            ctypes.byref(result),
        )
        if not succeeded:
            self.raise_last_error("SendMessageTimeoutW failed or timed out")
        return int(result.value)

    def check_matching_bitness(self, process_handle: int) -> None:
        current_process = ctypes.c_void_p(-1)
        python_wow64 = ctypes.c_int()
        explorer_wow64 = ctypes.c_int()
        if not self.kernel32.IsWow64Process(current_process, ctypes.byref(python_wow64)):
            self.raise_last_error("Could not determine Python process architecture")
        if not self.kernel32.IsWow64Process(process_handle, ctypes.byref(explorer_wow64)):
            self.raise_last_error("Could not determine Explorer process architecture")
        if python_wow64.value != explorer_wow64.value:
            raise RuntimeError(
                "Python and Explorer have different bitness. Install/run 64-bit Python "
                "to control 64-bit Explorer."
            )

    def enable_ansi_colours(self) -> bool:
        handle = self.kernel32.GetStdHandle(STD_OUTPUT_HANDLE & 0xFFFFFFFF)
        mode = ctypes.c_uint32()
        if not handle or not self.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(self.kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))


class RemoteMemory:
    def __init__(self, api: Win32Api, process_handle: int, size: int) -> None:
        self.api = api
        self.process_handle = process_handle
        address = api.kernel32.VirtualAllocEx(process_handle, None, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not address:
            api.raise_last_error("VirtualAllocEx failed")
        self.address = int(address)

    def write(self, address: int, data: bytes) -> None:
        local_buffer = ctypes.create_string_buffer(data, len(data))
        written = ctypes.c_size_t()
        succeeded = self.api.kernel32.WriteProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            ctypes.cast(local_buffer, ctypes.c_void_p),
            len(data),
            ctypes.byref(written),
        )
        if not succeeded or written.value != len(data):
            self.api.raise_last_error("WriteProcessMemory failed")

    def write_struct(self, address: int, struct: ctypes.Structure) -> None:
        self.write(address, ctypes.string_at(ctypes.byref(struct), ctypes.sizeof(struct)))

    def read(self, address: int, size: int) -> bytes:
        local_buffer = ctypes.create_string_buffer(size)
        received = ctypes.c_size_t()
        succeeded = self.api.kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            ctypes.cast(local_buffer, ctypes.c_void_p),
            size,
            ctypes.byref(received),
        )
        if not succeeded:
            self.api.raise_last_error("ReadProcessMemory failed")
        return local_buffer.raw[: received.value]

    def close(self) -> None:
        if self.address:
            self.api.kernel32.VirtualFreeEx(self.process_handle, ctypes.c_void_p(self.address), 0, MEM_RELEASE)
            self.address = 0

    def __enter__(self) -> RemoteMemory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class DesktopManager:
    def __init__(self, timeout_ms: int = 2000) -> None:
        if os.name != "nt":
            raise RuntimeError("Chromatic Sorter runs only on Windows 10/11.")
        try:
            import win32api
            import win32gui
            import win32process
        except ImportError as exc:
            raise RuntimeError("pywin32 is required; install it with: py -m pip install pywin32") from exc

        self.win32api = win32api
        self.win32gui = win32gui
        self.api = Win32Api()
        self.timeout_ms = timeout_ms
        self.process_handle = None
        self.hwnd = self._find_list_view()
        _, self.process_id = win32process.GetWindowThreadProcessId(self.hwnd)
        access = PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_LIMITED_INFORMATION
        self.process_handle = self.api.kernel32.OpenProcess(access, False, self.process_id)
        if not self.process_handle:
            self.api.raise_last_error("OpenProcess could not open Explorer")
        try:
            self.api.check_matching_bitness(self.process_handle)
            spacing = self.api.send_timeout(self.hwnd, LVM_GETITEMSPACING, 0, 0, timeout_ms) & 0xFFFFFFFF
            self.cell_width = spacing & 0xFFFF
            self.cell_height = (spacing >> 16) & 0xFFFF
            if not self.cell_width or not self.cell_height:
                raise RuntimeError("Explorer returned invalid desktop icon spacing.")
        except Exception:
            self.close()
            raise

    def _find_list_view(self) -> int:
        win32gui = self.win32gui
        candidates: list[int] = []
        progman = win32gui.FindWindow("Progman", None)
        if progman:
            candidates.append(progman)
        win32gui.EnumWindows(lambda hwnd, _: candidates.append(hwnd), None)
        visited: set[int] = set()
        for top_window in candidates:
            if top_window in visited:
                continue
            visited.add(top_window)
            def_view = win32gui.FindWindowEx(top_window, 0, "SHELLDLL_DefView", None)
            if def_view:
                list_view = win32gui.FindWindowEx(def_view, 0, "SysListView32", None)
                if list_view:
                    return list_view
        raise RuntimeError("Could not find the desktop SysListView32 control in Explorer.")

    def _send_pointer_message(self, message: int, wparam: int, remote_address: int) -> int:
        return self.api.send_timeout(self.hwnd, message, wparam, remote_address, self.timeout_ms)

    def read_items(self) -> list[tuple[int, str, Point]]:
        count = self.api.send_timeout(self.hwnd, LVM_GETITEMCOUNT, 0, 0, self.timeout_ms)
        item_size = ctypes.sizeof(LVITEMW)
        text_bytes = MAX_TEXT_CHARS * ctypes.sizeof(ctypes.c_wchar)
        with RemoteMemory(self.api, self.process_handle, item_size + text_bytes + ctypes.sizeof(POINT)) as remote:
            text_address = remote.address + item_size
            point_address = text_address + text_bytes
            items = []
            for index in range(count):
                item = LVITEMW(iItem=index, pszText=text_address, cchTextMax=MAX_TEXT_CHARS)
                remote.write_struct(remote.address, item)
                length = self._send_pointer_message(LVM_GETITEMTEXTW, index, remote.address)
                raw = remote.read(text_address, min(length, MAX_TEXT_CHARS - 1) * ctypes.sizeof(ctypes.c_wchar))
                name = raw.decode("utf-16-le", errors="replace")

                self._send_pointer_message(LVM_GETITEMPOSITION, index, point_address)
                point = POINT.from_buffer_copy(remote.read(point_address, ctypes.sizeof(POINT)))
                items.append((index, name, Point(point.x, point.y)))
        return items

    def auto_arrange_enabled(self) -> bool:
        return bool(self.win32gui.GetWindowLong(self.hwnd, GWL_STYLE) & LVS_AUTOARRANGE)

    def grid(self, positions: Iterable[Point]) -> Grid:
        win32api, win32gui = self.win32api, self.win32gui
        monitor = win32api.MonitorFromPoint((0, 0), MONITOR_DEFAULTTOPRIMARY)
        left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
        left, top = win32gui.ScreenToClient(self.hwnd, (left, top))
        right, bottom = win32gui.ScreenToClient(self.hwnd, (right, bottom))

        offsets = Counter(
            ((point.x - left) % self.cell_width, (point.y - top) % self.cell_height)
            for point in positions
            if left <= point.x < right and top <= point.y < bottom
        )
        offset_x, offset_y = offsets.most_common(1)[0][0] if offsets else (0, 0)
        columns = (right - left - offset_x) // self.cell_width
        rows = (bottom - top - offset_y) // self.cell_height
        return Grid(Point(left + offset_x, top + offset_y), self.cell_width, self.cell_height,
                    max(1, columns), max(1, rows))

    def apply_positions(self, moves: Iterable[tuple[int, Point]], originals: dict[int, Point], grid: Grid) -> int:
        if self.auto_arrange_enabled():
            raise RuntimeError(
                "Explorer has 'Auto arrange icons' enabled, which would undo the layout immediately. "
                "Right-click the desktop > View, untick it, and run the command again."
            )
        spare = (grid.point((column, row)) for row in range(grid.rows) for column in range(grid.columns))
        sequence = plan_move_sequence(moves, originals, spare)
        moved: list[int] = []
        with RemoteMemory(self.api, self.process_handle, ctypes.sizeof(POINT)) as remote:
            try:
                for index, position in sequence:
                    remote.write_struct(remote.address, POINT(position.x, position.y))
                    self._send_pointer_message(LVM_SETITEMPOSITION32, index, remote.address)
                    moved.append(index)
            except Exception:
                for index in reversed(list(dict.fromkeys(moved))):
                    old = originals[index]
                    try:
                        remote.write_struct(remote.address, POINT(old.x, old.y))
                        self._send_pointer_message(LVM_SETITEMPOSITION32, index, remote.address)
                    except Exception:
                        pass
                raise
        return len(set(moved))

    def close(self) -> None:
        if self.process_handle:
            self.api.kernel32.CloseHandle(self.process_handle)
            self.process_handle = None

    def __enter__(self) -> DesktopManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class DesktopResolver:
    def __init__(self) -> None:
        try:
            import pythoncom
            import win32com.client
            from win32com.shell import shell
        except ImportError as exc:
            raise RuntimeError("pywin32 is required; install it with: py -m pip install pywin32") from exc

        pythoncom.CoInitialize()
        wscript = win32com.client.Dispatch("WScript.Shell")
        desktop = shell.SHGetDesktopFolder()
        self._by_label: dict[str, list[ShellEntry]] = {}
        for pidl in desktop.EnumObjects(0, SHCONTF_FOLDERS | SHCONTF_NONFOLDERS | SHCONTF_INCLUDEHIDDEN) or ():
            try:
                label = desktop.GetDisplayNameOf(pidl, SHGDN_NORMAL)
                parse_name = desktop.GetDisplayNameOf(pidl, SHGDN_FORPARSING)
                _, (_, icon_index, _, _, _) = shell.SHGetFileInfo(pidl, 0, SHGFI_PIDL | SHGFI_SYSICONINDEX)
            except pythoncom.com_error:
                continue
            target, details = self._read_target(wscript, parse_name)
            entry = ShellEntry(label, parse_name, icon_index, target, " ".join((label, parse_name, details)))
            self._by_label.setdefault(label.casefold(), []).append(entry)
        for entries in self._by_label.values():
            entries.sort(key=lambda entry: not entry.is_file)

    @staticmethod
    def _read_target(wscript, path: str) -> tuple[str | None, str]:
        suffix = Path(path).suffix.casefold()
        if suffix == ".lnk":
            try:
                shortcut = wscript.CreateShortcut(path)
                target = os.path.expandvars(shortcut.TargetPath) or None
                return target, " ".join((target or "", shortcut.Arguments, shortcut.WorkingDirectory))
            except Exception:
                return None, ""
        if suffix == ".url":
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read(path, encoding="utf-8")
                section = next((name for name in parser.sections() if name.casefold() == "internetshortcut"), None)
                url = parser.get(section, "URL", fallback=None) if section else None
                return url, url or ""
            except (OSError, UnicodeDecodeError, configparser.Error):
                return None, ""
        return (path, "") if os.path.isfile(path) else (None, "")

    def take(self, label: str) -> ShellEntry | None:
        entries = self._by_label.get(label.casefold())
        return entries.pop(0) if entries else None


class Categorizer:
    def __init__(self, keywords: dict[str, Iterable[str]]) -> None:
        self.patterns = []
        for category, words in keywords.items():
            words = [word.casefold() for word in words if word.strip()]
            if words:
                alternation = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
                self.patterns.append((category, re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])")))

    @classmethod
    def load(cls, path: Path | None) -> Categorizer:
        keywords = {category: list(words) for category, words in DEFAULT_CATEGORY_KEYWORDS.items()}
        if path is not None:
            try:
                extra = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Could not read categories file {path}: {exc}") from exc
            unknown = set(extra) - set(keywords) if isinstance(extra, dict) else set()
            if not isinstance(extra, dict) or unknown or not all(isinstance(w, list) for w in extra.values()):
                raise RuntimeError(
                    f"Categories file must map {', '.join(keywords)} to keyword lists "
                    f"(unknown: {', '.join(sorted(unknown)) or 'none'})."
                )
            for category, words in extra.items():
                keywords[category] = [*words, *keywords[category]]
        return cls(keywords)

    def classify(self, text: str) -> str:
        text = text.casefold()
        return next((category for category, pattern in self.patterns if pattern.search(text)), "Other")


class IconAnalyzer:
    def __init__(self, api: Win32Api) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required; install it with: py -m pip install Pillow") from exc
        self.Image = Image
        self.api = api
        self._cache: dict[int, ColorProfile | None] = {}
        image_list = ctypes.c_void_p()
        result = api.shell32.SHGetImageList(SHIL_EXTRALARGE, ctypes.byref(IID_IImageList), ctypes.byref(image_list))
        if result != 0 or not image_list.value:
            raise OSError(f"SHGetImageList failed (HRESULT 0x{result & 0xFFFFFFFF:08X})")
        self._image_list = image_list
        self._get_icon = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
        )(10, "GetIcon")
        self._release = ctypes.WINFUNCTYPE(ctypes.c_ulong)(2, "Release")

    def close(self) -> None:
        if self._image_list:
            self._release(self._image_list)
            self._image_list = None

    def profile(self, icon_index: int) -> ColorProfile | None:
        if icon_index not in self._cache:
            icon = ctypes.c_void_p()
            if self._get_icon(self._image_list, icon_index, ILD_TRANSPARENT, ctypes.byref(icon)) != 0 or not icon.value:
                self._cache[icon_index] = None
            else:
                try:
                    self._cache[icon_index] = analyze_colors(self._render(icon.value))
                finally:
                    self.api.user32.DestroyIcon(icon)
        return self._cache[icon_index]

    def _draw(self, icon: int, background: int) -> bytes:
        gdi = self.api.gdi32
        header = BITMAPINFOHEADER(
            biSize=ctypes.sizeof(BITMAPINFOHEADER),
            biWidth=ICON_SIZE,
            biHeight=-ICON_SIZE,
            biPlanes=1,
            biBitCount=32,
            biCompression=0,
        )
        bitmap_info = BITMAPINFO(bmiHeader=header)
        dc = bitmap = old_bitmap = None
        try:
            dc = gdi.CreateCompatibleDC(None)
            bits = ctypes.c_void_p()
            bitmap = gdi.CreateDIBSection(dc, ctypes.byref(bitmap_info), 0, ctypes.byref(bits), None, 0)
            if not dc or not bitmap or not bits.value:
                self.api.raise_last_error("Could not create a DIB for icon rendering")
            old_bitmap = gdi.SelectObject(dc, bitmap)
            ctypes.memset(bits, background, ICON_SIZE * ICON_SIZE * 4)
            if not self.api.user32.DrawIconEx(dc, 0, 0, icon, ICON_SIZE, ICON_SIZE, 0, None, DI_NORMAL):
                self.api.raise_last_error("DrawIconEx failed")
            return ctypes.string_at(bits, ICON_SIZE * ICON_SIZE * 4)
        finally:
            if old_bitmap and dc:
                gdi.SelectObject(dc, old_bitmap)
            if bitmap:
                gdi.DeleteObject(bitmap)
            if dc:
                gdi.DeleteDC(dc)

    def _render(self, icon: int):
        on_black = self._draw(icon, 0x00)
        on_white = self._draw(icon, 0xFF)
        pixels = bytearray(len(on_black))
        for offset in range(0, len(on_black), 4):
            blue, green, red = on_black[offset:offset + 3]
            difference = sum(on_white[offset:offset + 3]) - (blue + green + red)
            alpha = max(0, min(255, 255 - round(difference / 3)))
            if alpha:
                pixels[offset:offset + 4] = bytes((
                    min(255, red * 255 // alpha), min(255, green * 255 // alpha), min(255, blue * 255 // alpha), alpha,
                ))
        return self.Image.frombytes("RGBA", (ICON_SIZE, ICON_SIZE), bytes(pixels))


def _circular_distance(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def analyze_colors(image) -> ColorProfile | None:
    rgba = image.convert("RGBA")
    raw = rgba.tobytes()
    hsv = rgba.convert("RGB").convert("HSV").tobytes()
    bins = [0.0] * 36
    colourful: list[tuple[float, float, int, int, int, int, int]] = []
    visible = 0
    totals = [0, 0, 0]
    for pixel in range(len(raw) // 4):
        red, green, blue, alpha = raw[pixel * 4:pixel * 4 + 4]
        if alpha < 128:
            continue
        visible += 1
        totals[0] += red
        totals[1] += green
        totals[2] += blue
        hue_byte, saturation, value = hsv[pixel * 3:pixel * 3 + 3]
        if saturation >= MIN_SATURATION and value >= MIN_VALUE:
            hue = hue_byte * 360.0 / 256.0
            weight = (saturation / 255.0) * (value / 255.0)
            bins[int(hue // 10) % 36] += weight
            colourful.append((hue, weight, red, green, blue, saturation, value))

    if not visible:
        return None
    if len(colourful) < visible * MIN_COLOURFUL_FRACTION:
        mean = tuple(round(total / visible) for total in totals)
        return ColorProfile(None, 0.0, (0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]) / 255.0, mean)

    peak = max(range(36), key=lambda i: bins[i - 1] + bins[i] + bins[(i + 1) % 36])
    centre = peak * 10 + 5
    in_peak = [pixel for pixel in colourful if _circular_distance(pixel[0], centre) <= 20]
    total_weight = sum(pixel[1] for pixel in in_peak)
    x = sum(math.cos(math.radians(pixel[0])) * pixel[1] for pixel in in_peak)
    y = sum(math.sin(math.radians(pixel[0])) * pixel[1] for pixel in in_peak)
    rgb = tuple(round(sum(pixel[channel] * pixel[1] for pixel in in_peak) / total_weight) for channel in (2, 3, 4))
    return ColorProfile(
        math.degrees(math.atan2(y, x)) % 360.0,
        sum(pixel[5] for pixel in in_peak) / len(in_peak) / 255.0,
        sum(pixel[6] for pixel in in_peak) / len(in_peak) / 255.0,
        rgb,
    )


def rainbow_key(item: DesktopItem) -> tuple:
    color = item.color
    if color is None:
        return (2, 0.0, 0.0, item.name.casefold())
    if color.hue is None:
        return (1, -color.value, 0.0, item.name.casefold())
    return (0, (color.hue + HUE_START_OFFSET) % 360, -color.value, item.name.casefold())


class LayoutEngine:
    CORNERS = {
        "Productivity": ("top", "left"),
        "Development": ("top", "right"),
        "Utilities": ("bottom", "left"),
        "Gaming": ("bottom", "right"),
    }

    def __init__(self, grid: Grid) -> None:
        self.grid = grid
        self.notes: list[str] = []

    def place(self, layout: str, items: list[DesktopItem], pillars: int = 2) -> list[tuple[DesktopItem, Cell]]:
        if len(items) > self.grid.capacity:
            raise RuntimeError(
                f"The desktop grid has {self.grid.capacity} cells for {len(items)} icons. "
                "Use smaller desktop icons (right-click desktop > View) or remove some icons."
            )
        if layout == "rainbow":
            cells = [(column, row) for row in range(self.grid.rows) for column in range(self.grid.columns)]
            return list(zip(sorted(items, key=rainbow_key), cells))
        if layout == "borders":
            return self._borders(items)
        if layout == "circle":
            return self._circle(items)
        if layout == "pillars":
            return self._pillars(items, pillars)
        if layout == "corners":
            return self._corners(items)
        raise ValueError(f"Unknown layout: {layout}")

    def _pillars(self, items: list[DesktopItem], count: int) -> list[tuple[DesktopItem, Cell]]:
        columns, rows = self.grid.columns, self.grid.rows
        if not 2 <= count <= 6:
            raise ValueError("--pillars must be between 2 and 6.")
        per_pillar = math.ceil(len(items) / count)
        width = max(1, math.ceil(per_pillar / rows))
        side = count // 2
        starts = [pillar * (width + 1) for pillar in range(side)]
        if count % 2:
            starts.append((columns - width) // 2)
        starts += [columns - width - pillar * (width + 1) for pillar in reversed(range(side))]
        if starts[0] < 0 or any(right < left + width + 1 for left, right in zip(starts, starts[1:])):
            raise RuntimeError(
                f"{count} pillars {width} icons wide do not fit in {columns} columns; try fewer pillars."
            )

        ordered = sorted(items, key=rainbow_key)
        placed: list[tuple[DesktopItem, Cell]] = []
        for pillar, start in enumerate(starts):
            size = len(items) // count + (1 if pillar < len(items) % count else 0)
            top = (rows - math.ceil(size / width)) // 2
            cells = [(column, row) for row in range(top, rows) for column in range(start, start + width)]
            chunk, ordered = ordered[:size], ordered[size:]
            placed.extend(zip(chunk, cells))
        return placed

    def _circle(self, items: list[DesktopItem]) -> list[tuple[DesktopItem, Cell]]:
        chosen: list[Cell] = []
        depth = 0
        remaining = len(items)
        while remaining:
            ring = self._ring(depth)
            if len(ring) <= remaining:
                chosen += ring
                remaining -= len(ring)
            else:
                chosen += [ring[index * len(ring) // remaining] for index in range(remaining)]
                remaining = 0
            depth += 1
        if depth > 1:
            self.notes.append(
                f"{len(items)} icons do not fit on the outer edge ({len(self._ring(0))} cells); "
                f"the circle is {depth} icons thick."
            )

        centre_x = (self.grid.columns - 1) * self.grid.cell_width / 2
        centre_y = (self.grid.rows - 1) * self.grid.cell_height / 2
        start = math.atan2(-centre_y, -centre_x)

        def around(cell: Cell) -> tuple[float, float]:
            dx = cell[0] * self.grid.cell_width - centre_x
            dy = cell[1] * self.grid.cell_height - centre_y
            return (round((math.atan2(dy, dx) - start) % math.tau, 9), -math.hypot(dx, dy))

        return list(zip(sorted(items, key=rainbow_key), sorted(chosen, key=around)))

    def _ring(self, depth: int) -> list[Cell]:
        left, top = depth, depth
        right, bottom = self.grid.columns - 1 - depth, self.grid.rows - 1 - depth
        if left > right or top > bottom:
            return []
        if top == bottom:
            return [(column, top) for column in range(left, right + 1)]
        if left == right:
            return [(left, row) for row in range(top, bottom + 1)]
        cells = [(column, top) for column in range(left, right + 1)]
        cells += [(right, row) for row in range(top + 1, bottom + 1)]
        cells += [(column, bottom) for column in range(right - 1, left - 1, -1)]
        cells += [(left, row) for row in range(bottom - 1, top, -1)]
        return cells

    def _borders(self, items: list[DesktopItem]) -> list[tuple[DesktopItem, Cell]]:
        cells: list[Cell] = []
        depth = 0
        while len(cells) < len(items):
            cells += self._ring(depth)
            depth += 1
        if depth > 1:
            self.notes.append(
                f"{len(items)} icons do not fit on the outer edge ({len(self._ring(0))} cells); "
                f"the frame is {depth} icons thick."
            )
        return list(zip(sorted(items, key=rainbow_key), cells))

    def _corners(self, items: list[DesktopItem]) -> list[tuple[DesktopItem, Cell]]:
        columns, rows = self.grid.columns, self.grid.rows
        if columns < 2 or rows < 2:
            raise RuntimeError("The desktop grid must be at least two cells wide and two cells tall for corners.")
        groups: dict[str, list[DesktopItem]] = {category: [] for category in [*self.CORNERS, "Other"]}
        for item in items:
            groups.get(item.category, groups["Other"]).append(item)

        used: set[Cell] = set()
        placed: list[tuple[DesktopItem, Cell]] = []
        top_rows = list(range(0, (rows + 1) // 2))
        bottom_rows = list(range(rows - 1, (rows + 1) // 2 - 1, -1))
        for category, (vertical, horizontal) in self.CORNERS.items():
            group = sorted(groups[category], key=rainbow_key)
            row_order = top_rows if vertical == "top" else bottom_rows
            column_order = range(columns) if horizontal == "left" else range(columns - 1, -1, -1)
            free = [(column, row) for column in column_order for row in row_order if (column, row) not in used]
            if len(group) > len(free):
                raise RuntimeError(f"Not enough room in the {vertical} half of the screen for {len(group)} {category} icons.")
            for item, cell in zip(group, free):
                placed.append((item, cell))
                used.add(cell)

        centre = (columns - 1) / 2
        free_cells = sorted(
            ((column, row) for column in range(columns) for row in range(rows) if (column, row) not in used),
            key=lambda cell: (abs(cell[0] - centre), cell[0], cell[1]),
        )
        placed.extend(zip(sorted(groups["Other"], key=rainbow_key), free_cells))
        return placed


def plan_move_sequence(
    moves: Iterable[tuple[int, Point]], current: dict[int, Point], spare: Iterable[Point]
) -> list[tuple[int, Point]]:
    position = dict(current)
    occupant = {point: index for index, point in position.items()}
    pending = {index: point for index, point in moves if position.get(index) != point}
    targets = set(pending.values())
    parking = [point for point in spare if point not in occupant and point not in targets]
    sequence: list[tuple[int, Point]] = []

    def move(index: int, point: Point) -> None:
        if occupant.get(position.get(index)) == index:
            del occupant[position[index]]
        position[index] = point
        occupant[point] = index
        sequence.append((index, point))

    while pending:
        ready = [index for index, point in pending.items() if point not in occupant]
        for index in ready:
            move(index, pending.pop(index))
        if ready:
            continue
        blocker = next((occupant[point] for point in pending.values() if occupant[point] in pending), None)
        if blocker is None or not parking:
            for index in list(pending):
                move(index, pending.pop(index))
            break
        move(blocker, parking.pop())
    return sequence


def save_backup(raw_items: list[tuple[int, str, Point]], directory: Path = BACKUP_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = directory / f"backup-{now:%Y%m%d-%H%M%S}.json"
    data = {
        "created": now.isoformat(timespec="seconds"),
        "icons": [{"name": name, "x": point.x, "y": point.y} for _, name, point in raw_items],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def latest_backup(directory: Path = BACKUP_DIR) -> Path:
    backups = sorted(directory.glob("backup-*.json"))
    if not backups:
        raise RuntimeError(f"No backups found in {directory}. Backups are created by --apply and `backup`.")
    return backups[-1]


def restore_moves(raw_items: list[tuple[int, str, Point]], backup: Path) -> tuple[list[tuple[int, Point]], int]:
    try:
        saved = json.loads(backup.read_text(encoding="utf-8"))["icons"]
        by_name: dict[str, list[Point]] = {}
        for entry in saved:
            by_name.setdefault(entry["name"], []).append(Point(int(entry["x"]), int(entry["y"])))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not read backup {backup}: {exc}") from exc
    moves = []
    for index, name, _ in raw_items:
        if by_name.get(name):
            moves.append((index, by_name[name].pop(0)))
    return moves, len(raw_items) - len(moves)


def collect_items(raw_items: list[tuple[int, str, Point]], categorizer: Categorizer) -> list[DesktopItem]:
    resolver = DesktopResolver()
    analyzer = IconAnalyzer(Win32Api())
    try:
        items = []
        for index, name, position in raw_items:
            entry = resolver.take(name)
            color = analyzer.profile(entry.icon_index) if entry else None
            category = categorizer.classify(entry.search_text if entry else name)
            items.append(DesktopItem(
                index, name, position, entry.parse_name if entry else None,
                entry.target if entry else None, category, color,
            ))
        return items
    finally:
        analyzer.close()


def render_map(grid: Grid, placements: list[tuple[DesktopItem, Cell]], ansi: bool) -> str:
    by_cell = {cell: item for item, cell in placements}
    lines = []
    for row in range(grid.rows):
        line = []
        for column in range(grid.columns):
            item = by_cell.get((column, row))
            if item is None:
                line.append("\x1b[2m· \x1b[0m" if ansi else ". ")
            elif item.color is None:
                line.append("? ")
            elif ansi:
                red, green, blue = item.color.rgb
                line.append(f"\x1b[38;2;{red};{green};{blue}m██\x1b[0m")
            else:
                line.append(item.color.family[0] + " ")
        lines.append("  " + "".join(line))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Arrange Windows desktop icons by colour or category. "
        "Layouts are previewed by default; pass --apply to move the icons.",
        epilog="Every --apply saves a backup first; undo with `restore`.",
    )
    parser.add_argument(
        "command",
        choices=("rainbow", "pillars", "circle", "corners", "borders", "restore", "backup"),
        help="rainbow: hue-sorted grid | pillars: rainbow split into vertical pillars | "
        "circle: colour wheel around the screen edges | corners: categories in corners | borders: rainbow frame | "
        "restore: undo using the newest (or --file) backup | backup: save current positions",
    )
    parser.add_argument("--apply", action="store_true", help="move the icons (layouts only preview without this)")
    parser.add_argument("--pillars", "-n", type=int, choices=range(2, 7), metavar="N",
                        help="number of pillars for the `pillars` layout, 2-6 (default 2)")
    parser.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--verbose", "-v", action="store_true", help="list every icon with its colour and category")
    parser.add_argument("--categories", type=Path, help='JSON file adding keywords, e.g. {"Gaming": ["factorio"]}')
    parser.add_argument("--file", type=Path, help="backup file for `restore` (default: newest)")
    parser.add_argument("--no-color", action="store_true", help="plain-text preview without ANSI colours")
    parser.add_argument("--timeout", type=int, default=2000, help="Explorer message timeout in milliseconds")
    return parser


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().casefold() in {"y", "yes"}
    except EOFError:
        return False


def run(args: argparse.Namespace) -> int:
    if not 100 <= args.timeout <= 30000:
        raise RuntimeError("--timeout must be between 100 and 30000 milliseconds.")
    if os.name != "nt" or sys.getwindowsversion().major < 10:
        raise RuntimeError("Chromatic Sorter supports Windows 10/11 only.")
    if args.file and args.command != "restore":
        raise RuntimeError("--file is only used with `restore`.")
    if args.pillars is not None and args.command != "pillars":
        raise RuntimeError("--pillars is only used with the `pillars` layout.")

    enable_dpi_awareness()
    with DesktopManager(args.timeout) as desktop:
        raw_items = desktop.read_items()
        if not raw_items:
            print("No desktop icons were found.")
            return 0

        if args.command == "backup":
            print(f"Saved {len(raw_items)} icon positions to {save_backup(raw_items)}")
            return 0

        if args.command == "restore":
            backup = args.file or latest_backup()
            moves, unmatched = restore_moves(raw_items, backup)
            print(f"Restoring {len(moves)} icon positions from {backup}")
            if unmatched:
                print(f"Note: {unmatched} current icon(s) are not in the backup and stay where they are.")
            if not confirm("Restore these positions?", args.yes):
                print("No changes made.")
                return 0
            originals = {index: point for index, _, point in raw_items}
            desktop.apply_positions(moves, originals, desktop.grid(originals.values()))
            print("Desktop icon positions restored.")
            return 0

        categorizer = Categorizer.load(args.categories)
        items = collect_items(raw_items, categorizer)
        grid = desktop.grid(item.position for item in items)
        engine = LayoutEngine(grid)
        placements = engine.place(args.command, items, args.pillars or 2)

        ansi = not args.no_color and desktop.api.enable_ansi_colours()
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        layout_name = f"{args.command} ({args.pillars or 2})" if args.command == "pillars" else args.command
        print(f"Layout: {layout_name} | Icons: {len(items)} | Grid: {grid.columns} x {grid.rows} "
              f"cells of {grid.cell_width} x {grid.cell_height} px")
        print(render_map(grid, placements, ansi))
        categories = Counter(item.category for item in items)
        families = Counter(item.color.family if item.color else "Unknown" for item in items)
        print("Categories: " + ", ".join(f"{name} {count}" for name, count in categories.most_common()))
        print("Colours:    " + ", ".join(f"{name} {count}" for name, count in families.most_common()))
        if args.verbose:
            for item, cell in placements:
                color = item.color
                if color is None:
                    hue = "unknown"
                elif color.hue is None:
                    hue = color.family
                else:
                    hue = f"{color.family} {color.hue:5.1f} deg"
                print(f"  ({cell[0]:2}, {cell[1]:2})  {item.category:<12} {hue:<18} {item.name}")
        for note in engine.notes:
            print(f"Note: {note}")
        if desktop.auto_arrange_enabled():
            print("Warning: 'Auto arrange icons' is on; turn it off (desktop > View) before applying.")

        if not args.apply:
            print("Preview only. Re-run with --apply to move the icons.")
            return 0
        if not confirm("Move desktop icons to these positions?", args.yes):
            print("No changes made.")
            return 0

        backup = save_backup(raw_items)
        originals = {item.index: item.position for item in items}
        moved = desktop.apply_positions(((item.index, grid.point(cell)) for item, cell in placements), originals, grid)
        print(f"Moved {moved} icons. Backup saved to {backup}")
        print(f"Undo with: py {Path(sys.argv[0]).name} restore")
        return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
