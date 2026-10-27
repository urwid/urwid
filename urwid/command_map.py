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

"""Mapping of keystrokes to the abstract commands that widgets act on."""

from __future__ import annotations

import enum
import typing
from collections.abc import MutableMapping

if typing.TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Self


class Command(enum.StrEnum):
    """Abstract commands that a :class:`CommandMap` maps keystrokes to."""

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
    WORD_LEFT = "cursor word left"
    WORD_RIGHT = "cursor word right"
    DELETE_WORD_LEFT = "delete word left"
    DELETE_WORD_RIGHT = "delete word right"
    DELETE_TO_LINE_START = "delete to start of line"
    DELETE_TO_LINE_END = "delete to end of line"


REDRAW_SCREEN: typing.Literal[Command.REDRAW_SCREEN] = Command.REDRAW_SCREEN
CURSOR_UP: typing.Literal[Command.UP] = Command.UP
CURSOR_DOWN: typing.Literal[Command.DOWN] = Command.DOWN
CURSOR_LEFT: typing.Literal[Command.LEFT] = Command.LEFT
CURSOR_RIGHT: typing.Literal[Command.RIGHT] = Command.RIGHT
CURSOR_PAGE_UP: typing.Literal[Command.PAGE_UP] = Command.PAGE_UP
CURSOR_PAGE_DOWN: typing.Literal[Command.PAGE_DOWN] = Command.PAGE_DOWN
CURSOR_MAX_LEFT: typing.Literal[Command.MAX_LEFT] = Command.MAX_LEFT
CURSOR_MAX_RIGHT: typing.Literal[Command.MAX_RIGHT] = Command.MAX_RIGHT
ACTIVATE: typing.Literal[Command.ACTIVATE] = Command.ACTIVATE


class CommandMap(MutableMapping[str, str | Command | None]):
    """
    dict-like object for looking up commands from keystrokes.

    Default values:

    :kbd:`tab`, :kbd:`ctrl n`
        ``'next selectable'``
    :kbd:`shift tab`, :kbd:`ctrl p`
        ``'prev selectable'``
    :kbd:`ctrl l`
        ``'redraw screen'``
    :kbd:`esc`
        ``'menu'``
    :kbd:`up`, :kbd:`down`, :kbd:`left`, :kbd:`right`
        ``'cursor up'``, ``'cursor down'``, ``'cursor left'``, ``'cursor right'``
    :kbd:`page up`, :kbd:`page down`
        ``'cursor page up'``, ``'cursor page down'``
    :kbd:`home`, :kbd:`end`
        ``'cursor max left'``, ``'cursor max right'``
    :kbd:`space`, :kbd:`enter`
        ``'activate'``

    Only containers created with ``select_navigation=True`` handle ``'next selectable'`` and
    ``'prev selectable'``, see :ref:`select-navigation`.

    :class:`Edit` also handles these readline-style commands, which no key is mapped to by default:
    ``'cursor word left'``, ``'cursor word right'``, ``'delete word left'``, ``'delete word right'``,
    ``'delete to start of line'`` and ``'delete to end of line'``.
    A word is a run of letters, digits and underscores, and a line ends at a newline.

    * ``'delete word left'`` stops at punctuation, as readline's ``backward-kill-word`` (:kbd:`meta backspace`) does,
      except that an underscore is part of a word here.
      It is not bash's :kbd:`ctrl w` (``unix-word-rubout``), which deletes back to the previous whitespace.
    * ``'delete to start of line'`` and ``'delete to end of line'`` work on lines that end at a newline.
      ``'cursor max left'`` and ``'cursor max right'`` move to the edge of the screen row instead,
      so on a wrapped line they stop earlier than the deletes reach.

    >>> cm = CommandMap()
    >>> cm.bind(Command.WORD_LEFT, "meta b")
    >>> cm.bind(Command.DELETE_TO_LINE_START, "ctrl u")
    """

    def __iter__(self) -> Iterator[str]:
        """Iterate over the keystrokes currently mapped to a command."""
        return iter(self._command)

    def __len__(self) -> int:
        """Return the number of keystrokes currently mapped to a command."""
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
        """Initialize the command map with the class's default key-to-command bindings."""
        self._command = self._command_defaults.copy()

    def restore_defaults(self) -> None:
        """Reset the command map to the class's default key-to-command bindings."""
        self._command = self._command_defaults.copy()

    def __getitem__(self, key: str) -> str | Command | None:
        """Return the command mapped to `key`, or None if unmapped."""
        return self._command.get(key, None)

    def __setitem__(self, key: str, command: str | Command | None) -> None:
        """Set command in the command map.

        :param key: keystroke
        :param command: command aliad. If the alias is `None`, the command is removed from the map.
        """
        if command is None:
            if key in self._command:
                del self._command[key]
            return
        self._command[key] = command

    def __delitem__(self, key: str) -> None:
        """Remove the command mapping for `key`."""
        del self._command[key]

    def bind(self, command: str | Command, *keys: str) -> None:
        """Bind ``keys`` to ``command``, refusing a key that is already bound to a different command.

        A key already bound to ``command`` is accepted.
        Item assignment (``command_map[key] = command``) remains the way to rebind a key on purpose.

        >>> cm = CommandMap()
        >>> cm.bind("quit", "q", "ctrl c")
        >>> cm.bind("quit", "ctrl l")
        Traceback (most recent call last):
        ...
        ValueError: Key 'ctrl l' is already bound to 'redraw screen', cannot also bind it to 'quit'

        :param command: the command to bind.
        :param keys: keystrokes to bind to ``command``, added to those it already has.
        :raises ValueError: a key in ``keys`` is already bound to a different command;
            the command map is left unchanged.
        """
        for key in keys:
            bound = self._command.get(key)
            if bound is not None and bound != command:
                raise ValueError(
                    f"Key {key!r} is already bound to {str(bound)!r}, cannot also bind it to {str(command)!r}"
                )
        for key in keys:
            self._command[key] = command

    def clear_command(self, command: str | Command) -> None:
        """Remove every keystroke currently mapped to ``command``."""
        dk = [k for k, v in self._command.items() if v == command]
        for k in dk:
            del self._command[k]

    def copy(self) -> Self:
        """Return a new copy of this CommandMap, likely so we can modify it separate from a shared one."""
        c = self.__class__()
        c._command = dict(self._command)  # pylint: disable=protected-access
        return c


command_map = CommandMap()  # shared command mappings
