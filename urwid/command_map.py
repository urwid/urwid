# Urwid CommandMap class
#    Copyright (C) 2004-2011  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/

from __future__ import annotations

import enum
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Self


class Command(str, enum.Enum):
    REDRAW_SCREEN = "redraw screen"
    UP = "cursor up"
    DOWN = "cursor down"
    LEFT = "cursor left"
    RIGHT = "cursor right"
    PAGE_UP = "cursor page up"
    PAGE_DOWN = "cursor page down"
    MAX_LEFT = "cursor max left"
    MAX_RIGHT = "cursor max right"
    ACTIVATE = "activate"
    MENU = "menu"
    SELECT_NEXT = "next selectable"
    SELECT_PREVIOUS = "prev selectable"


REDRAW_SCREEN = Command.REDRAW_SCREEN
CURSOR_UP = Command.UP
CURSOR_DOWN = Command.DOWN
CURSOR_LEFT = Command.LEFT
CURSOR_RIGHT = Command.RIGHT
CURSOR_PAGE_UP = Command.PAGE_UP
CURSOR_PAGE_DOWN = Command.PAGE_DOWN
CURSOR_MAX_LEFT = Command.MAX_LEFT
CURSOR_MAX_RIGHT = Command.MAX_RIGHT
ACTIVATE = Command.ACTIVATE


class CommandMap(typing.Mapping[str, typing.Union[str, Command, None]]):
    """
    dict-like object for looking up commands from keystrokes

    Default values (key: command)::

        'tab':       'next selectable',
        'ctrl n':    'next selectable',
        'shift tab': 'prev selectable',
        'ctrl p':    'prev selectable',
        'ctrl l':    'redraw screen',
        'esc':       'menu',
        'up':        'cursor up',
        'down':      'cursor down',
        'left':      'cursor left',
        'right':     'cursor right',
        'page up':   'cursor page up',
        'page down': 'cursor page down',
        'home':      'cursor max left',
        'end':       'cursor max right',
        ' ':         'activate',
        'enter':     'activate',
    """

    def __iter__(self) -> Iterator[str]:
        return iter(self._command)

    def __len__(self) -> int:
        return len(self._command)

    _command_defaults: typing.ClassVar[dict[str, str | Command]] = {
        "tab": Command.SELECT_NEXT,
        "ctrl n": Command.SELECT_NEXT,
        "shift tab": Command.SELECT_PREVIOUS,
        "ctrl p": Command.SELECT_PREVIOUS,
        "ctrl l": Command.REDRAW_SCREEN,
        "esc": Command.MENU,
        "up": Command.UP,
        "down": Command.DOWN,
        "left": Command.LEFT,
        "right": Command.RIGHT,
        "page up": Command.PAGE_UP,
        "page down": Command.PAGE_DOWN,
        "home": Command.MAX_LEFT,
        "end": Command.MAX_RIGHT,
        " ": Command.ACTIVATE,
        "enter": Command.ACTIVATE,
    }

    def __init__(self) -> None:
        self._command = dict(self._command_defaults)

    def restore_defaults(self) -> None:
        self._command = dict(self._command_defaults)

    def __getitem__(self, key: str) -> str | Command | None:
        return self._command.get(key, None)

    def __setitem__(self, key, command: str | Command) -> None:
        self._command[key] = command

    def __delitem__(self, key: str) -> None:
        del self._command[key]

    def clear_command(self, command: str | Command) -> None:
        dk = [k for k, v in self._command.items() if v == command]
        for k in dk:
            del self._command[k]

    def copy(self) -> Self:
        """
        Return a new copy of this CommandMap, likely so we can modify
        it separate from a shared one.
        """
        c = self.__class__()
        c._command = dict(self._command)  # pylint: disable=protected-access
        return c


command_map = CommandMap()  # shared command mappings
