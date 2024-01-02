from __future__ import annotations

import enum
import typing
from ctypes import POINTER, Structure, Union, windll
from ctypes.wintypes import BOOL, CHAR, DWORD, HANDLE, LPDWORD, SHORT, UINT, WCHAR, WORD

# https://docs.microsoft.com/de-de/windows/console/getstdhandle
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11

# https://docs.microsoft.com/de-de/windows/console/setconsolemode
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
DISABLE_NEWLINE_AUTO_RETURN = 0x0008
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
ENABLE_WINDOW_INPUT = 0x0008


class COORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/coord-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("X", SHORT),
        ("Y", SHORT),
    ]


class SMALL_RECT(Structure):
    """https://docs.microsoft.com/en-us/windows/console/small-rect-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("Left", SHORT),
        ("Top", SHORT),
        ("Right", SHORT),
        ("Bottom", SHORT),
    ]


class CONSOLE_SCREEN_BUFFER_INFO(Structure):
    """https://docs.microsoft.com/en-us/windows/console/console-screen-buffer-info-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("dwSize", COORD),
        ("dwCursorPosition", COORD),
        ("wAttributes", WORD),
        ("srWindow", SMALL_RECT),
        ("dwMaximumWindowSize", COORD),
    ]


class uChar(Union):
    """https://docs.microsoft.com/en-us/windows/console/key-event-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("AsciiChar", CHAR),
        ("UnicodeChar", WCHAR),
    ]


class KEY_EVENT_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/key-event-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("bKeyDown", BOOL),
        ("wRepeatCount", WORD),
        ("wVirtualKeyCode", WORD),
        ("wVirtualScanCode", WORD),
        ("uChar", uChar),
        ("dwControlKeyState", DWORD),
    ]


class MOUSE_EVENT_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/mouse-event-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("dwMousePosition", COORD),
        ("dwButtonState", DWORD),
        ("dwControlKeyState", DWORD),
        ("dwEventFlags", DWORD),
    ]


class MouseButtonState(enum.IntFlag):
    """https://learn.microsoft.com/en-us/windows/console/mouse-event-record-str"""

    FROM_LEFT_1ST_BUTTON_PRESSED = 0x0001
    RIGHTMOST_BUTTON_PRESSED = 0x0002
    FROM_LEFT_2ND_BUTTON_PRESSED = 0x0004
    FROM_LEFT_3RD_BUTTON_PRESSED = 0x0008
    FROM_LEFT_4TH_BUTTON_PRESSED = 0x0010


class MouseEventFlags(enum.IntFlag):
    """https://learn.microsoft.com/en-us/windows/console/mouse-event-record-str"""

    BUTTON_PRESSED = 0x0000  # Default action, used in examples, but not in official enum
    MOUSE_MOVED = 0x0001
    DOUBLE_CLICK = 0x0002
    MOUSE_WHEELED = 0x0004
    MOUSE_HWHEELED = 0x0008


class WINDOW_BUFFER_SIZE_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/window-buffer-size-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [("dwSize", COORD)]


class MENU_EVENT_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/menu-event-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [("dwCommandId", UINT)]


class FOCUS_EVENT_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/focus-event-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [("bSetFocus", BOOL)]


class Event(Union):
    """https://docs.microsoft.com/en-us/windows/console/input-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [
        ("KeyEvent", KEY_EVENT_RECORD),
        ("MouseEvent", MOUSE_EVENT_RECORD),
        ("WindowBufferSizeEvent", WINDOW_BUFFER_SIZE_RECORD),
        ("MenuEvent", MENU_EVENT_RECORD),
        ("FocusEvent", FOCUS_EVENT_RECORD),
    ]


class INPUT_RECORD(Structure):
    """https://docs.microsoft.com/en-us/windows/console/input-record-str"""

    _fields_: typing.ClassVar[list[tuple[str, type]]] = [("EventType", WORD), ("Event", Event)]


class EventType(enum.IntFlag):
    KEY_EVENT = 0x0001
    MOUSE_EVENT = 0x0002
    WINDOW_BUFFER_SIZE_EVENT = 0x0004
    MENU_EVENT = 0x0008
    FOCUS_EVENT = 0x0010


# https://docs.microsoft.com/de-de/windows/console/getstdhandle
GetStdHandle = windll.kernel32.GetStdHandle
GetStdHandle.argtypes = [DWORD]
GetStdHandle.restype = HANDLE

# https://docs.microsoft.com/de-de/windows/console/getconsolemode
GetConsoleMode = windll.kernel32.GetConsoleMode
GetConsoleMode.argtypes = [HANDLE, LPDWORD]
GetConsoleMode.restype = BOOL

# https://docs.microsoft.com/de-de/windows/console/setconsolemode
SetConsoleMode = windll.kernel32.SetConsoleMode
SetConsoleMode.argtypes = [HANDLE, DWORD]
SetConsoleMode.restype = BOOL

# https://docs.microsoft.com/de-de/windows/console/readconsoleinput
ReadConsoleInputW = windll.kernel32.ReadConsoleInputW
# ReadConsoleInputW.argtypes = [HANDLE, POINTER(INPUT_RECORD), DWORD, LPDWORD]
ReadConsoleInputW.restype = BOOL

# https://docs.microsoft.com/en-us/windows/console/getconsolescreenbufferinfo
GetConsoleScreenBufferInfo = windll.kernel32.GetConsoleScreenBufferInfo
GetConsoleScreenBufferInfo.argtypes = [HANDLE, POINTER(CONSOLE_SCREEN_BUFFER_INFO)]
GetConsoleScreenBufferInfo.restype = BOOL
