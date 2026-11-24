# Urwid common display code
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


"""Base classes and signals shared by every display module."""

from __future__ import annotations

import abc
import logging
import os
import sys
import types
import typing

from urwid import signals
from urwid.display.common import _depth
from urwid.display.common._attr_spec import (
    _RESOLVED_ATTRS_LIMIT,
    AttrSpec,
)
from urwid.display.common._colors import (
    _DEFAULT_COLOR_NAMES,
    DEFAULT,
    INHERIT,
)
from urwid.util import LayeredAttr, StoppingContext

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Mapping
    from typing import Literal

    from urwid import Canvas

    # One register_palette() item:
    # (name, like_other_name)
    # or the 3, 4 or 6 positional arguments of register_palette_entry().
    # A name is any hashable value, None being the default attribute.
    PaletteEntry = (
        tuple[Hashable, Hashable]
        | tuple[Hashable, str, str]
        | tuple[Hashable, str, str, str | tuple[str, ...] | None]
        | tuple[
            Hashable,
            str,
            str,
            str | tuple[str, ...] | None,
            str | None,
            str | None,
        ]
    )


IS_WINDOWS = sys.platform == "win32"

# for replacing unprintable bytes with '?'
UNPRINTABLE_TRANS_TABLE = bytes.maketrans(bytes(range(32)), b"?" * 32)
# for replacing decoded C1 control characters (U+0080-U+009F) with '?'
UNPRINTABLE_C1_TRANS_TABLE = str.maketrans(dict.fromkeys(range(0x80, 0xA0), "?"))


# signals sent by BaseScreen
UPDATE_PALETTE_ENTRY = "update palette entry"
INPUT_DESCRIPTORS_CHANGED = "input descriptors changed"


class RealTerminal:
    """Mixin providing access to the real terminal's signal key settings."""

    def __init__(self) -> None:
        """Initialize with no signal keys saved yet."""
        super().__init__()
        self._signal_keys_set = False
        self._old_signal_keys: tuple[bytes, bytes, bytes, bytes, bytes] | None = None

    if IS_WINDOWS:

        def tty_signal_keys(
            self,
            intr: Literal["undefined"] | int | bytes | None = None,
            quit: Literal["undefined"] | int | bytes | None = None,  # noqa: A002  # pylint: disable=redefined-builtin
            start: Literal["undefined"] | int | bytes | None = None,
            stop: Literal["undefined"] | int | bytes | None = None,
            susp: Literal["undefined"] | int | bytes | None = None,
            fileno: int | None = None,
        ) -> tuple[bytes, bytes, bytes, bytes, bytes] | None:
            r"""Read and/or set the tty's signal character settings.

            This function returns the current settings as a tuple of one-byte strings,
            as termios reports them, which may be passed back to restore them.

            Use the string 'undefined' to unmap keys from their signals.
            The value None is used when no change is being made.
            Setting signal keys is done using the integer ascii
            code for the key, eg.  3 for CTRL+C, or its one-byte string, eg. b"\x03".

            If this function is called after start() has been called
            then the original settings will be restored when stop()
            is called.
            """
            return None

    else:

        def tty_signal_keys(
            self,
            intr: Literal["undefined"] | int | bytes | None = None,
            quit: Literal["undefined"] | int | bytes | None = None,  # noqa: A002  # pylint: disable=redefined-builtin
            start: Literal["undefined"] | int | bytes | None = None,
            stop: Literal["undefined"] | int | bytes | None = None,
            susp: Literal["undefined"] | int | bytes | None = None,
            fileno: int | None = None,
        ) -> tuple[bytes, bytes, bytes, bytes, bytes] | None:
            r"""Read and/or set the tty's signal character settings.

            This function returns the current settings as a tuple of one-byte strings,
            as termios reports them, which may be passed back to restore them.

            Use the string 'undefined' to unmap keys from their signals.
            The value None is used when no change is being made.
            Setting signal keys is done using the integer ascii
            code for the key, eg.  3 for CTRL+C, or its one-byte string, eg. b"\x03".

            If this function is called after start() has been called
            then the original settings will be restored when stop()
            is called.
            """
            import termios

            if fileno is None:
                fileno = sys.stdin.fileno()
            if not os.isatty(fileno):
                return None

            tattr = termios.tcgetattr(fileno)
            sattr = tattr[6]
            skeys = (
                sattr[termios.VINTR],
                sattr[termios.VQUIT],
                sattr[termios.VSTART],
                sattr[termios.VSTOP],
                sattr[termios.VSUSP],
            )

            # termios reports these keys as bytes, and the tuple returned below is passed back
            # here to restore them, so check the type first: comparing bytes with str raises
            # BytesWarning under `python -bb`.
            if isinstance(intr, str) and intr == "undefined":
                intr = 0
            if isinstance(quit, str) and quit == "undefined":
                quit = 0  # noqa: A001
            if isinstance(start, str) and start == "undefined":
                start = 0
            if isinstance(stop, str) and stop == "undefined":
                stop = 0
            if isinstance(susp, str) and susp == "undefined":
                susp = 0

            if intr is not None:
                tattr[6][termios.VINTR] = intr
            if quit is not None:
                tattr[6][termios.VQUIT] = quit
            if start is not None:
                tattr[6][termios.VSTART] = start
            if stop is not None:
                tattr[6][termios.VSTOP] = stop
            if susp is not None:
                tattr[6][termios.VSUSP] = susp

            if any(item is not None for item in (intr, quit, start, stop, susp)):
                termios.tcsetattr(fileno, termios.TCSADRAIN, tattr)
                self._signal_keys_set = True

            return skeys


class ScreenError(Exception):
    """Raised for errors in :class:`BaseScreen` and its subclasses."""


class PaletteEntrySpecs(typing.NamedTuple):
    """The specifications one palette entry is drawn with, one per number of colors.

    The position of each field is the index :meth:`BaseScreen.resolve_attr` takes.
    """

    #: 16 colors
    basic: AttrSpec
    #: monochrome
    mono: AttrSpec
    #: 88 colors
    high_88: AttrSpec
    #: 256 colors
    high_256: AttrSpec
    #: true color
    high_true: AttrSpec


class InputClosedError(RuntimeError):
    """Raised when the screen's input reaches end of file.

    A terminal that hangs up is one cause.
    It is a :exc:`RuntimeError`, so a handler that catches :exc:`RuntimeError` around :meth:`MainLoop.run` catches it
    too.
    """


class BaseScreen(abc.ABC, metaclass=signals.MetaSignals):
    """Base class for Screen classes (display.raw.Screen, ..., etc.)."""

    signals: typing.ClassVar[list[str]] = [UPDATE_PALETTE_ENTRY, INPUT_DESCRIPTORS_CHANGED]

    def __init__(self) -> None:
        """Initialize an unstarted screen with an empty palette."""
        super().__init__()

        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

        self._palette: dict[Hashable, PaletteEntrySpecs] = {}
        # resolve_attr() results by (attr, index), and _drawn_attr() results by (attr, index, draws)
        self._resolved_attrs: dict[tuple[Hashable, ...], AttrSpec] = {}
        self._started: bool = False

    @property
    def started(self) -> bool:
        """Return whether the screen has been started and not yet stopped."""
        return self._started

    @property
    def palette(self) -> Mapping[Hashable, PaletteEntrySpecs]:
        """Return a read-only view of the registered palette entries.

        The view follows later changes to the palette.
        Change the palette with :meth:`register_palette` and :meth:`register_palette_entry`.

        >>> from urwid.display.html_fragment import HtmlGenerator
        >>> screen = HtmlGenerator()
        >>> screen.register_palette_entry("title", "white", "dark blue")
        >>> screen.palette["title"].basic
        AttrSpec('white', 'dark blue')

        :returns: per entry name, the specifications it is drawn with; ``None`` names the default attribute.
        """
        return types.MappingProxyType(self._palette)

    def start(self, *args: typing.Any, **kwargs: typing.Any) -> StoppingContext:
        """Set up the screen.

        If the screen has already been started, does nothing.

        May be used as a context manager, in which case :meth:`stop` will
        automatically be called at the end of the block:

            with screen.start():
                ...

        You shouldn't override this method in a subclass; instead, override
        :meth:`_start`.

        When :meth:`_start` raises, :meth:`_stop` undoes what it set up and the screen is left stopped,
        so nothing that only a started screen sends, such as a window title, reaches a terminal left unprepared.

        :raises BaseException: whatever :meth:`_start` raises,
            or whatever :meth:`_stop` raises while undoing it, with the error of :meth:`_start` as its context.
        """
        if not self._started:
            self._started = True
            try:
                self._start(*args, **kwargs)
            except BaseException:
                try:
                    self._stop()
                finally:
                    self._started = False
                    signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
                raise
        return StoppingContext(self)

    def _start(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        """Perform the actual setup of the screen. Subclasses should override this method."""

    def stop(self) -> None:
        """Tear down the screen if it has been started.

        Emits ``INPUT_DESCRIPTORS_CHANGED`` once the screen is marked stopped,
        so an event loop hooked to the screen stops watching its input.

        You shouldn't override this method; override :meth:`_stop`.
        """
        if not self._started:
            return
        self._stop()
        self._started = False
        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

    def _stop(self) -> None:
        """Perform actual teardown of the screen. Subclasses should override this method.

        It also runs after a :meth:`_start` that raised, so it undoes only the setup that was done.
        """

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """Enable or disable tracking of mouse movement events. A no-op here; subclasses override it."""

    @abc.abstractmethod
    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Draw *canvas* of the given *size* to the screen. Subclasses must implement this method."""

    def clear(self) -> None:
        """Clear the screen if possible.

        Force the screen to be completely repainted on the next call to draw_screen().
        """

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the terminal dimensions (num columns, num rows).

        Default (fallback) is 80x24.
        """
        return 80, 24

    def register_palette(self, palette: Iterable[PaletteEntry], *, replace: bool = False) -> None:
        """Register a set of palette entries.

        With *replace*, the entries that *palette* does not name are removed once all of its entries are registered.
        A removed name is drawn in the terminal's default colors, as a name that was never registered is.
        The ``None`` entry is kept unless *palette* names it, so the screen keeps its default attribute.

        >>> from urwid.display.html_fragment import HtmlGenerator
        >>> screen = HtmlGenerator()
        >>> screen.register_palette([("title", "white", "dark blue"), ("body", "black", "light gray")])
        >>> screen.register_palette([("body", "white", "black")], replace=True)
        >>> list(screen.palette)
        [None, 'body']

        :param palette: a list of (name, like_other_name) or
            (name, foreground, background, mono, foreground_high, background_high) tuples
        :param replace: remove the entries that *palette* does not name
        :raises ScreenError: an entry is neither a 2-, 3-, 4- nor 6-tuple, or copies a name that is not registered yet.
            The entries before it stay registered, and with *replace* no entry is removed.

            The (name, like_other_name) format will copy the settings
            from the palette entry like_other_name, which must appear
            before this tuple in the list.

            The mono and foreground/background_high values are
            optional ie. the second tuple format may have 3, 4 or 6
            values.  See register_palette_entry() for a description
            of the tuple values.
        """
        names: set[Hashable] = {None}
        for item in palette:
            if len(item) in {3, 4, 6}:
                # pyrefly: ignore[bad-argument-type]  # a union of tuples of different lengths
                self.register_palette_entry(*item)
                names.add(item[0])
                continue
            if len(item) != 2:
                raise ScreenError(f"Invalid register_palette entry: {item!r}")
            name, like_name = item
            if like_name not in self._palette:
                raise ScreenError(f"palette entry '{like_name}' doesn't exist")
            signals.emit_signal(self, UPDATE_PALETTE_ENTRY, name, *self._palette[like_name])
            self._palette[name] = self._palette[like_name]
            self._resolved_attrs.clear()
            names.add(name)
        if not replace:
            return
        removed = [name for name in self._palette if name not in names]
        if not removed:
            return
        # what a removed name is drawn with from now on, sent so that displays caching per name draw it again
        default_specs = PaletteEntrySpecs(
            *(AttrSpec(DEFAULT, DEFAULT, colors) for colors in (16, 1, 88, 256, 16777216))
        )
        for name in removed:
            signals.emit_signal(self, UPDATE_PALETTE_ENTRY, name, *default_specs)
            del self._palette[name]
            self._resolved_attrs.clear()

    def register_palette_entry(
        self,
        name: Hashable,
        foreground: str,
        background: str,
        mono: str | tuple[str, ...] | None = None,
        foreground_high: str | None = None,
        background_high: str | None = None,
    ) -> None:
        """Register a single palette entry.

        :param name: new entry/attribute name, any hashable value; ``None`` names the default attribute

        :param foreground: a string containing a comma-separated foreground
            color and settings

            Color values:
            'default' (use the terminal's default foreground),
            'inherit' (take the color from the enclosing attribute),
            'black', 'dark red', 'dark green', 'brown', 'dark blue',
            'dark magenta', 'dark cyan', 'light gray', 'dark gray',
            'light red', 'light green', 'yellow', 'light blue',
            'light magenta', 'light cyan', 'white'

            Settings:
            'bold', 'underline', 'blink', 'standout', 'strikethrough'

            Some terminals use 'bold' for bright colors.  Most terminals
            ignore the 'blink' setting.  If the color is not given then
            'default' will be assumed.

        :param background: a string containing the background color

            Background color values:
            'default' (use the terminal's default background),
            'inherit' (take the color from the enclosing attribute),
            'black', 'dark red', 'dark green', 'brown', 'dark blue',
            'dark magenta', 'dark cyan', 'light gray'

        :param mono: a comma-separated string containing monochrome terminal
            settings (see "Settings" above.)

            None = no terminal settings (same as 'default')

        :param foreground_high: a string containing a comma-separated
            foreground color and settings, standard foreground
            colors (see "Color values" above) or high-colors may
            be used

            High-color example values:
            '#009' (0% red, 0% green, 60% red, like HTML colors)
            '#fcc' (100% red, 80% green, 80% blue)
            'g40' (40% gray, decimal), 'g#cc' (80% gray, hex),
            '#000', 'g0', 'g#00' (black),
            '#fff', 'g100', 'g#ff' (white)
            'h8' (color number 8), 'h255' (color number 255)

            None = use foreground parameter value

        :param background_high: a string containing the background color,
            standard background colors (see "Background colors" above)
            or high-colors (see "High-color example values" above)
            may be used

            None = use background parameter value
        """
        basic = AttrSpec(foreground, background, 16)

        if isinstance(mono, tuple):
            # old style of specifying mono attributes was to put them in a tuple.  convert to comma-separated string
            mono = ",".join(mono)
        if mono is None:
            mono = DEFAULT
        if basic.foreground_inherit or basic.background_inherit:
            # monochrome has no colors to inherit, but the settings are combined the same way
            mono_settings = [part for part in mono.split(",") if part.strip() not in _DEFAULT_COLOR_NAMES]
            mono_spec = AttrSpec(
                ",".join((INHERIT if basic.foreground_inherit else DEFAULT, *mono_settings)),
                INHERIT if basic.background_inherit else DEFAULT,
                1,
            )
        else:
            mono_spec = AttrSpec(mono, DEFAULT, 1)

        if foreground_high is None:
            foreground_high = foreground
        if background_high is None:
            background_high = background

        high_256 = AttrSpec(foreground_high, background_high, 256)
        high_true = AttrSpec(foreground_high, background_high, 16777216)  # 2**24 is not Literal

        # 'hX' where X > 15 are different in 88/256 color, use
        # basic colors for 88-color mode if high colors are specified
        # in this way (also avoids crash when X > 87)
        def large_h(desc: str) -> bool:
            if not desc.startswith("h"):
                return False
            if "," in desc:
                desc = desc.split(",", 1)[0]
            num = int(desc[1:], 10)
            return num > 15

        if large_h(foreground_high) or large_h(background_high):
            high_88 = basic
        else:
            high_88 = AttrSpec(foreground_high, background_high, 88)

        entry = PaletteEntrySpecs(basic, mono_spec, high_88, high_256, high_true)
        signals.emit_signal(self, UPDATE_PALETTE_ENTRY, name, *entry)
        self._palette[name] = entry
        self._resolved_attrs.clear()

    def resolve_attr(self, attr: Hashable, index: int) -> AttrSpec:
        """Return the :class:`AttrSpec` to draw a canvas run with display attribute *attr*.

        Starting from the palette entry of ``None``, each layer of *attr* (a palette name, an :class:`AttrSpec`
        or a :class:`LayeredAttr`), outermost first, is placed over the result so far with
        :meth:`AttrSpec.layered_over`. A name missing from the palette is drawn with 'default' colors,
        hiding the layers under it.
        At index 2 the layers are placed in 88-color mode; at any other index each color keeps its kind,
        so layers of different color modes give a palette entry beside a 24-bit color.

        :param attr: display attribute of a canvas run
        :param index: position in the palette entry tuple: 0 for 16 colors, 1 for monochrome,
            2 for 88 colors, 3 for 256 colors, 4 for true color
        :raises IndexError: *index* is outside 0-4 and a layer is a palette name.
        """
        key = (attr, index)
        if (found := self._resolved_attrs.get(key)) is not None:
            return found
        # 88-color numbers differ from 256-color ones, so an 88-color screen keeps its own encoding
        return self.__remember(key, self.__layered(attr, index, colors=88 if index == 2 else None))

    def _drawn_attr(self, attr: Hashable, index: int, draws: _depth.Draws) -> AttrSpec:
        """Return the :class:`AttrSpec` a display that draws *draws* colors draws a canvas run with *attr* in.

        The layers of *attr* are placed as :meth:`resolve_attr` places them, with the palette entries of *index*,
        but each color keeps its kind at every index.
        The result is then converted once to the colors the display draws: a color it has is kept, and any other is
        approximated by the nearest one it has.
        When a subclass overrides :meth:`resolve_attr`, its result is the one converted.

        :param attr: display attribute of a canvas run
        :param index: position in the palette entry tuple, as for :meth:`resolve_attr`
        :param draws: the colors the display draws: 1, 8 (the curses color pairs), 16, 88, 256 or 2**24
        :raises IndexError: *index* is outside 0-4 and a layer is a palette name.
        """
        key = (attr, index, draws)
        if (found := self._resolved_attrs.get(key)) is not None:
            return found
        if type(self).resolve_attr is not BaseScreen.resolve_attr:
            spec = self.resolve_attr(attr, index)
        else:
            spec = self.__layered(attr, index, colors=None)
        return self.__remember(key, _depth.convert(spec, draws))

    def __layered(self, attr: Hashable, index: int, *, colors: Literal[88] | None) -> AttrSpec:
        """Return the layers of *attr* placed over each other with :meth:`AttrSpec.layered_over` in *colors*."""
        if isinstance(attr, LayeredAttr):
            layers: tuple[Hashable, ...] = (*attr.layers, None)
        elif attr is None:
            layers = (None,)
        else:
            layers = (attr, None)
        result: AttrSpec | None = None
        for layer in reversed(layers):
            if isinstance(layer, AttrSpec):
                spec = layer
            elif (entry := self._palette.get(layer)) is not None:
                spec = entry[index]
            elif layer is None:
                continue
            else:
                self.logger.debug(f"Undefined attribute: {layer!r}")
                spec = AttrSpec(DEFAULT, DEFAULT)
            result = spec if result is None else spec.layered_over(result, colors=colors)
        return AttrSpec(DEFAULT, DEFAULT) if result is None else result

    def __remember(self, key: tuple[Hashable, ...], result: AttrSpec) -> AttrSpec:
        """Keep *result* in the bounded cache of resolved attributes under *key*, and return it."""
        if len(self._resolved_attrs) >= _RESOLVED_ATTRS_LIMIT:
            self._resolved_attrs.clear()
        self._resolved_attrs[key] = result
        return result
