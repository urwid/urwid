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

import dataclasses
import enum
import types
import typing
from collections.abc import MutableMapping

if typing.TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
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


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class CommandInfo:
    """Description of a command, for building a keyboard help screen."""

    #: What the command does, as one line shown to the user.
    help_text: str
    #: Heading the command is listed under.
    category: str


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

    Every standard command also has a :class:`CommandInfo` with its help text and category, and
    :meth:`register` adds one for an application's own command. Together with :meth:`keys_for`
    they are what a keyboard help screen is built from:

    >>> cm = CommandMap()
    >>> cm.register("quit", "q", "ctrl c", help_text="Quit the program", category="Application")
    >>> for command, info in cm.command_info.items():
    ...     if info.category == "Application":
    ...         print(info.category, cm.keys_for(command), info.help_text)
    Application ('q', 'ctrl c') Quit the program
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

    _command_info_defaults: typing.ClassVar[dict[str | Command, CommandInfo]] = {
        Command.REDRAW_SCREEN: CommandInfo("Redraw the screen", "Screen"),
        Command.UP: CommandInfo("Move up", "Navigation"),
        Command.DOWN: CommandInfo("Move down", "Navigation"),
        Command.LEFT: CommandInfo("Move left", "Navigation"),
        Command.RIGHT: CommandInfo("Move right", "Navigation"),
        Command.PAGE_UP: CommandInfo("Move up by one page", "Navigation"),
        Command.PAGE_DOWN: CommandInfo("Move down by one page", "Navigation"),
        Command.MAX_LEFT: CommandInfo("Move to the start", "Navigation"),
        Command.MAX_RIGHT: CommandInfo("Move to the end", "Navigation"),
        Command.ACTIVATE: CommandInfo("Activate the focused widget", "Actions"),
        Command.MENU: CommandInfo("Open or close the menu", "Actions"),
        Command.SELECT_NEXT: CommandInfo("Focus the next selectable widget", "Focus"),
        Command.SELECT_PREVIOUS: CommandInfo("Focus the previous selectable widget", "Focus"),
    }

    def __init__(self) -> None:
        """Initialize the command map with the class's default bindings and command descriptions."""
        self._command = self._command_defaults.copy()
        self._command_info = self._command_info_defaults.copy()

    def __setstate__(self, state: dict[str, typing.Any]) -> None:
        """Restore a pickled command map; one pickled by an older release gets the default command descriptions."""
        self.__dict__.update(state)
        self.__dict__.setdefault("_command_info", self._command_info_defaults.copy())

    def restore_defaults(self) -> None:
        """Reset the command map to the class's default key-to-command bindings.

        Command descriptions are kept, including those added by :meth:`register`.
        """
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

    def register(
        self,
        command: str | Command,
        *keys: str,
        help_text: str,
        category: str,
    ) -> None:
        """Describe ``command`` and bind ``keys`` to it.

        A key already bound to ``command`` is accepted, and a description given earlier is replaced.
        Item assignment (``command_map[key] = command``) remains the way to rebind a key on purpose.

        :param command: the command to describe and bind.
        :param keys: keystrokes to bind to ``command``, added to those it already has.
        :param help_text: what the command does, as one line shown to the user.
        :param category: heading the command is listed under.
        :raises ValueError: a key in ``keys`` is already bound to a different command;
            the command map is left unchanged.
        """
        for key in keys:
            bound = self._command.get(key)
            if bound is not None and bound != command:
                raise ValueError(
                    f"Key {key!r} is already bound to {str(bound)!r}, cannot also bind it to {str(command)!r}"
                )
        self._command_info[command] = CommandInfo(help_text, category)
        for key in keys:
            self._command[key] = command

    @property
    def command_info(self) -> Mapping[str | Command, CommandInfo]:
        """Read-only view of the description of every described command, in the order they were first described.

        A command stays described when its keys are removed, so :meth:`keys_for` can return no keys for it.
        """
        return types.MappingProxyType(self._command_info)

    def keys_for(self, command: str | Command) -> tuple[str, ...]:
        """Return the keystrokes currently mapped to ``command``, in the order they were first added to the map."""
        return tuple(key for key, bound in self._command.items() if bound == command)

    def clear_command(self, command: str | Command) -> None:
        """Remove every keystroke currently mapped to ``command``."""
        dk = [k for k, v in self._command.items() if v == command]
        for k in dk:
            del self._command[k]

    def copy(self) -> Self:
        """Return a new copy of this CommandMap, likely so we can modify it separate from a shared one."""
        c = self.__class__()
        c._command = dict(self._command)  # pylint: disable=protected-access
        c._command_info = dict(self._command_info)  # pylint: disable=protected-access
        return c


command_map = CommandMap()  # shared command mappings
