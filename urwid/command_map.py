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
    LINE_START = "cursor line start"
    LINE_END = "cursor line end"
    DELETE_SPACE_WORD_LEFT = "delete space word left"
    DELETE_RIGHT = "delete char right"
    COMPLETE_NEXT = "complete next"
    COMPLETE_PREVIOUS = "complete previous"


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
    ``'cursor word left'``, ``'cursor word right'``, ``'cursor line start'``, ``'cursor line end'``,
    ``'delete word left'``, ``'delete word right'``, ``'delete space word left'``, ``'delete char right'``,
    ``'delete to start of line'`` and ``'delete to end of line'``.
    A word is a run of letters, digits and underscores, and a line ends at a newline.
    :meth:`bind_readline` maps the usual readline keys to them.
    An :class:`Edit` with a text completer handles ``'complete next'`` and ``'complete previous'``, which no key is
    mapped to by default either; see :attr:`Edit.text_completer`.

    * ``'delete word left'`` stops at punctuation, as readline's ``backward-kill-word`` (:kbd:`meta backspace`) does,
      except that an underscore is part of a word here.
    * ``'delete space word left'`` deletes back to the previous whitespace, as bash's :kbd:`ctrl w`
      (``unix-word-rubout``) does.
    * ``'cursor line start'``, ``'cursor line end'``, ``'delete to start of line'`` and ``'delete to end of line'``
      work on lines that end at a newline.
      ``'cursor max left'`` and ``'cursor max right'`` move to the edge of the screen row instead,
      so on a wrapped line they stop earlier.
    * ``'delete char right'`` deletes the character under the cursor, as :kbd:`delete` does.

    >>> cm = CommandMap()
    >>> cm.bind(Command.WORD_LEFT, "meta b")
    >>> cm.bind(Command.DELETE_TO_LINE_START, "ctrl u")
    >>> cm.bind(Command.COMPLETE_NEXT, "ctrl f")
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

    def bind_readline(self) -> None:
        """Bind the readline editing keys to the commands :class:`Edit` handles.

        ======================================  ==================================================
        keys                                    commands
        ======================================  ==================================================
        :kbd:`ctrl a`, :kbd:`ctrl e`            ``'cursor line start'``, ``'cursor line end'``
        :kbd:`meta b`, :kbd:`meta f`            ``'cursor word left'``, ``'cursor word right'``
        :kbd:`meta backspace`, :kbd:`meta d`    ``'delete word left'``, ``'delete word right'``
        :kbd:`ctrl u`, :kbd:`ctrl k`            ``'delete to start of line'``, ``'delete to end of line'``
        :kbd:`ctrl w`                           ``'delete space word left'``
        :kbd:`ctrl d`                           ``'delete char right'``
        ======================================  ==================================================

        No other widget handles these commands, so the keys reach the containers above an :class:`Edit` unchanged,
        and the shared command map can take them.

        >>> cm = CommandMap()
        >>> cm.bind_readline()
        >>> cm["ctrl a"]
        <Command.LINE_START: 'cursor line start'>
        >>> cm["ctrl k"] = "kill"
        >>> cm.bind_readline()
        Traceback (most recent call last):
        ...
        ValueError: Key 'ctrl k' is already bound to 'kill', cannot also bind it to 'delete to end of line'

        :raises ValueError: one of the keys is already bound to a different command; the command map is left
            unchanged.
        """
        staged = self.copy()
        staged.bind(Command.LINE_START, "ctrl a")
        staged.bind(Command.LINE_END, "ctrl e")
        staged.bind(Command.WORD_LEFT, "meta b")
        staged.bind(Command.WORD_RIGHT, "meta f")
        staged.bind(Command.DELETE_WORD_LEFT, "meta backspace")
        staged.bind(Command.DELETE_WORD_RIGHT, "meta d")
        staged.bind(Command.DELETE_TO_LINE_START, "ctrl u")
        staged.bind(Command.DELETE_TO_LINE_END, "ctrl k")
        staged.bind(Command.DELETE_SPACE_WORD_LEFT, "ctrl w")
        staged.bind(Command.DELETE_RIGHT, "ctrl d")
        self._command = staged._command  # pylint: disable=protected-access

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
