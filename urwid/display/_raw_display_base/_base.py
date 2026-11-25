# Urwid raw display module
#    Copyright (C) 2004-2009  Ian Ward
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


"""State, terminal properties and output stream of the raw display :class:`Screen`."""

from __future__ import annotations

import abc
import contextlib
import dataclasses
import enum
import os
import signal
import socket
import typing

from urwid import signals
from urwid.display import escape
from urwid.display._raw_display_base._detection import (
    TerminalProperties,
    _ColorCount,
    _environment_colors,
    detect_terminal_properties,
)
from urwid.display.common import (
    UPDATE_PALETTE_ENTRY,
    AttrSpec,
    BaseScreen,
    RealTerminal,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Mapping
    from types import FrameType
    from typing import Literal, Self

    from urwid import Canvas
    from urwid.display import common
    from urwid.display.common import Hyperlink


# signal has no SIGWINCH on Windows; _win32_raw_display passes its own signum explicitly, so this
# default is only ever actually used on POSIX.
_SIGWINCH = getattr(signal, "SIGWINCH", 28)

# most bytes of terminal input read per wake-up
_INPUT_READ_LIMIT = 65536


_T = typing.TypeVar("_T")


class _TerminalProperty(typing.Generic[_T]):
    """A screen attribute that reads and replaces one field of the screen's :class:`TerminalProperties`."""

    __slots__ = ("name",)

    def __init__(self) -> None:
        self.name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @typing.overload
    def __get__(self, instance: None, owner: type | None = None) -> Self: ...

    @typing.overload
    def __get__(self, instance: _ScreenBase, owner: type | None = None) -> _T: ...

    def __get__(self, instance: _ScreenBase | None, owner: type | None = None) -> _T | Self:
        if instance is None:
            return self
        return typing.cast("_T", getattr(instance._terminal_properties, self.name))

    def __set__(self, instance: _ScreenBase, value: _T) -> None:
        # the field is named at run time, so its type cannot be checked against the keyword;
        # a changed value draws the whole screen again, in the new colors and settings
        instance._replace_terminal_properties({self.name: value})
        instance._properties_set.add(self.name)

    def __delete__(self, instance: _ScreenBase) -> None:
        """Refuse to delete the setting, which every screen has.

        :raises AttributeError: always. ``mock.patch.object`` restores a patched attribute by deleting it, so a test
            assigns the setting, and its previous value back, instead.
        """
        message = f"{self.name} is a setting of every screen and cannot be deleted; assign it instead"
        raise AttributeError(message)


class _ColorProbe(enum.Enum):
    """The state of the rendition probe in one run of the screen; it is sent at most once per run."""

    #: not sent yet
    UNSENT = enum.auto()
    #: sent, and its Primary DA reply not read yet
    PENDING = enum.auto()
    #: answered, not needed, or ended by a stop
    FINISHED = enum.auto()


@dataclasses.dataclass(slots=True, weakref_slot=True)
class TermModes:
    """Terminal modes negotiated with the real host terminal (counterpart to `canvas.term.TermModes`).

    None: sentinel, resolved by a DECRPM reply (see escape.PrivateMode) or an explicit Screen.__init__ arg.
    """

    alternate_buffer: bool | None = None
    mouse_reporting: bool | None = None
    mouse_sgr_mode: bool | None = None
    focus_reporting: bool | None = None
    bracketed_paste: bool | None = None
    synchronized_output: bool | None = None
    grapheme_clustering: bool | None = None
    in_band_resize: bool | None = None
    # Set by Screen(alternate_scroll=...) only: None leaves the mode to the terminal, and no reply changes it.
    alternate_scroll: bool | None = None
    # Resolved by the replies to the keyboard protocol queries, which are sent only for Screen(extended_keys=True).
    kitty_keyboard: bool | None = None
    modify_other_keys: bool | None = None

    # escape.PrivateMode member -> the field it resolves.
    _FIELDS: typing.ClassVar[Mapping[str, str]] = {
        escape.PrivateMode.ALTERNATE_SCREEN_BUFFER: "alternate_buffer",
        escape.PrivateMode.MOUSE_REPORTING: "mouse_reporting",
        escape.PrivateMode.MOUSE_SGR_MODE: "mouse_sgr_mode",
        escape.PrivateMode.FOCUS_REPORTING: "focus_reporting",
        escape.PrivateMode.BRACKETED_PASTE: "bracketed_paste",
        escape.PrivateMode.SYNCHRONIZED_OUTPUT: "synchronized_output",
        escape.PrivateMode.GRAPHEME_CLUSTERING: "grapheme_clustering",
        escape.PrivateMode.IN_BAND_RESIZE: "in_band_resize",
    }

    def set_from_codes(self, *response: tuple[str, int]) -> frozenset[str]:
        """Apply DECRPM (mode, value) pairs; return the field names newly resolved to supported."""
        newly_supported = set()
        for mode, value in response:
            field = self._FIELDS.get(mode)
            if field is None:
                continue
            was_unresolved = getattr(self, field) is None
            supported = value in escape.DECRQM_SETTABLE_VALUES
            setattr(self, field, supported)
            if was_unresolved and supported:
                newly_supported.add(field)
        return frozenset(newly_supported)


@typing.runtime_checkable
class SupportsFileno(typing.Protocol):
    """Object that can be used to obtain an OS-level file descriptor."""

    def fileno(self) -> int:
        """Return the underlying OS-level file descriptor."""
        ...


class TextWriter(typing.Protocol):
    """Text output stream used by the raw display."""

    def write(self, data: str, /) -> object:
        """Write `data` to the stream."""

    def flush(self) -> object:
        """Flush buffered output to the stream."""


class _ScreenBase(BaseScreen, RealTerminal):
    """Hold the state of a raw display :class:`Screen` and write to its output stream.

    Every attribute the raw display layers keep per instance is set here, apart from the input timeout's class default.
    The layers above add attribute output, mode negotiation, input and drawing, and call only the layers below them.
    """

    __slots__ = (
        "_alternate_buffer",
        "_alternate_buffer_reported",
        "_alternate_scroll_reported",
        "_alternate_scroll_written",
        "_capabilities_answered",
        "_capability_query_pending",
        "_color_probe",
        "_colors_confirmed",
        "_colors_from_environment",
        "_cy",
        "_drawn_rows",
        "_hold_resize",
        "_in_band_resize",
        "_keyboard_protocol_enabled",
        "_keyboard_query_pending",
        "_last_cols_rows",
        "_mode_queries_pending",
        "_modified_palette_entries",
        "_modify_other_keys_reported",
        "_mouse_tracking_enabled",
        "_pal_escape",
        "_partial_codes",
        "_partial_read_time",
        "_properties_set",
        "_rendition",
        "_reported_cols_rows",
        "_resize_held_passes",
        "_resize_pipe_rd",
        "_resize_pipe_wr",
        "_resized",
        "_rows_used",
        "_screen_buf_canvas",
        "_setup_G1_done",
        "_start_complete",
        "_term_input_file",
        "_term_output_file",
        "_terminal_default_colors",
        "_terminal_properties",
        "_title",
        "_title_saved",
        "complete_wait",
        "extended_keys",
        "last_bstate",
        "max_wait",
        "maxrow",
        "modes",
        "prev_input_resize",
        "resize_wait",
        "screen_buf",
        "signal_handler_setter",
        "term",
    )

    _term_input_file: SupportsFileno

    _term_output_file: TextWriter

    _terminal_properties: TerminalProperties

    # the fields of the terminal properties the screen draws with, set directly or by set_terminal_properties()
    colors = _TerminalProperty[_ColorCount]()

    has_underline = _TerminalProperty[bool]()

    fg_bright_is_bold = _TerminalProperty[bool]()

    bg_bright_is_blink = _TerminalProperty[bool]()

    back_color_erase = _TerminalProperty[bool]()

    underline_styles = _TerminalProperty[bool]()

    hyperlinks = _TerminalProperty[bool]()

    @property
    def terminal_default_colors(self) -> tuple[str | None, str | None]:
        """Return the terminal's default foreground and background colors.

        Each is an X11 color spec, such as ``rgb:ffff/ffff/ffff``, as the terminal answered the OSC 10 and OSC 11
        queries, or None when it did not answer.
        The screen sends the queries as it starts, with the capability queries: not on the Linux console, and not when
        the application set both the color count and the underline styles.
        The :class:`~urwid.Terminal` widget answers its child's queries with them.
        """
        return self._terminal_default_colors.get(10), self._terminal_default_colors.get(11)

    def __init__(
        self,
        input: SupportsFileno,  # noqa: A002  # pylint: disable=redefined-builtin
        output: TextWriter,
        bracketed_paste_mode: bool | None = None,
        focus_reporting: bool | None = None,
        extended_keys: bool = False,
        *,
        in_band_resize: bool | None = None,
        alternate_scroll: bool | None = None,
        underline_styles: bool | None = None,
    ) -> None:
        """Initialize a screen that directly prints escape codes to an output terminal.

        :param input: the terminal input, read through its file descriptor.
        :param output: the terminal output, which the escape codes are written to.
        :param bracketed_paste_mode: enable bracketed paste (`begin`/`end paste` keystrokes).
            None (default) auto-detects via DECRQM and enables it once confirmed supported;
            pass True/False to force it without probing.
        :param focus_reporting: enable focus reporting (`focus in`/`focus out` keystrokes).
            None (default) auto-detects via DECRQM and enables it once confirmed supported;
            pass True/False to force it without probing.
        :param extended_keys: report the keys the legacy encodings cannot tell apart, such as ``'ctrl enter'``
            and ``'ctrl i'`` apart from ``'tab'``, through the keyboard protocol the terminal supports.
            Ctrl+C and Ctrl+Z then arrive as keys instead of signals; see :ref:`extended-keys`.
        :param in_band_resize: take the terminal size from the resize notifications the terminal sends in the input
            (DEC private mode 2048), as well as from ``SIGWINCH``; see :ref:`in-band-resize`.
            None (default) auto-detects via DECRQM and enables it once confirmed supported;
            pass True/False to force it without probing.
        :param alternate_scroll: whether the terminal sends the mouse wheel as cursor up and down keys
            while the screen runs (DEC private mode 1007), which it does only on the alternate screen
            and while the screen does not track the mouse.
            None (default) leaves the terminal's own setting.
            True/False set the mode when the screen starts,
            and the state the terminal reported is set back when it stops; without a report the mode stays as set.
        :param underline_styles: draw the underline styles and the underline colors of the display attributes;
            without them an underline is drawn single and in the text color.
            None (default) detects them by the terminfo entry of ``TERM``,
            and turns them on when the terminal's reply to a capability or version query shows them;
            pass True/False to force it.
        """
        super().__init__()

        self._partial_codes: list[int] = []
        # time.monotonic() of the read that left a sequence cut short:
        # get_input() decodes it as it is once no more of it arrived for complete_wait after that read
        self._partial_read_time = 0.0
        self.modes = TermModes(
            bracketed_paste=bracketed_paste_mode,
            focus_reporting=focus_reporting,
            in_band_resize=in_band_resize,
            alternate_scroll=alternate_scroll,
        )
        self.extended_keys = extended_keys
        # the alternate scroll mode the terminal reported before the screen set it, None while it reported none
        self._alternate_scroll_reported: bool | None = None
        # the screen set the alternate scroll mode and has not set it back yet
        self._alternate_scroll_written = False
        # the keyboard protocol queries were sent and the Primary DA reply that ends their answers has not arrived
        self._keyboard_query_pending = False
        # the XTVERSION and XTGETTCAP queries were sent and the Primary DA reply that ends their answers has not arrived
        self._capability_query_pending = False
        # the Primary DA reply after those queries arrived, so the terminal answered what it could
        self._capabilities_answered = False
        # the terminal's default foreground (10) and background (11) colors, as its OSC 10 and OSC 11 replies give them
        self._terminal_default_colors: dict[int, str] = {}
        # the terminal properties the application set, which no terminal reply changes
        self._properties_set: set[str] = set()
        # the private modes queried by the last start and not answered yet
        self._mode_queries_pending: set[str] = set()
        # the modifyOtherKeys value the terminal reported, written back when the screen stops
        self._modify_other_keys_reported: int | None = None
        self._keyboard_protocol_enabled: Literal["kitty", "modify other keys"] | None = None
        # SGR and OSC 8 escape sequences per canvas run attribute, filled as attributes are drawn
        self._pal_escape: dict[Hashable, tuple[str, str]] = {}
        self._modified_palette_entries: set[int] = set()
        # Connected through a weak reference: a bound method would be a reference cycle back to this screen,
        # keeping its sockets open until the cyclic garbage collector happened to run.
        signals.connect_signal(self, UPDATE_PALETTE_ENTRY, type(self)._on_update_palette_entry, weak_args=(self,))
        self.term = os.environ.get("TERM", "")
        self._terminal_properties = detect_terminal_properties(self.term, os.environ)
        # NO_COLOR, FORCE_COLOR or CLICOLOR decided the colour count, which no terminal reply changes then
        self._colors_from_environment = _environment_colors(os.environ) is not None
        # a reply to the rendition probe confirmed the colour count, which later guesses no longer change
        self._colors_confirmed = False
        self._color_probe = _ColorProbe.FINISHED
        # the terminal reported, in this run, that the alternate screen the screen switched to is set
        self._alternate_buffer_reported = False
        # the SGR sequence the last frame of this run left the terminal in, None while it is unknown
        self._rendition: str | None = None
        if underline_styles is not None:
            self._terminal_properties = dataclasses.replace(
                self._terminal_properties, underline_styles=underline_styles
            )
            self._properties_set.add("underline_styles")
        # the window title set_title() asked for, shown while the screen runs
        self._title: str | None = None
        # the title the terminal had before is saved, and is given back when the screen stops
        self._title_saved = False
        self.prev_input_resize = 0
        self.set_input_timeouts()
        self.screen_buf: list[list[tuple[Hashable, Literal["0", "U"] | None, bytes]]] | None = None
        # screen_buf with each attribute as its escape sequence: rows are compared by what the terminal shows,
        # so a palette change redraws only the rows it changes
        self._drawn_rows: list[list[tuple[str, Literal["0", "U"] | None, bytes]]] = []
        self._screen_buf_canvas: Canvas | None = None
        self._resized = False
        # set by the last read of terminal input: a resize may have input typed before it still waiting
        self._hold_resize = False
        # the input carries window size reports in order with the keys:
        # the terminal sends them while this screen has mode 2048 on, or this screen puts them there itself
        self._in_band_resize = False
        # the size the last window size report carried, until a SIGWINCH tells the system's size is newer
        self._reported_cols_rows: tuple[int, int] | None = None
        # the size get_cols_rows() last returned, which the application lays out at
        self._last_cols_rows: tuple[int, int] | None = None
        self._resize_held_passes = 0
        self.maxrow: int | None = None
        # the last _start() finished, so a stop moves the cursor below the frames to maxrow
        self._start_complete = False
        self._alternate_buffer = False
        self._mouse_tracking_enabled = False
        self.last_bstate = 0
        self._setup_G1_done = False
        self._rows_used: int | None = None
        self._cy = 0
        self.register_palette_entry(None, "default", "default")
        self.signal_handler_setter = signal.signal

        # Our connections to the world
        self._term_output_file = output
        self._term_input_file = input

        # pipe for signalling external event loops about resize events
        self._resize_pipe_rd, self._resize_pipe_wr = socket.socketpair()
        self._resize_pipe_rd.setblocking(False)
        self._resize_pipe_wr.setblocking(False)

    def __del__(self) -> None:
        self._resize_pipe_rd.close()
        self._resize_pipe_wr.close()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(input={self._term_input_file}, output={self._term_output_file})>"

    def _sigwinch_handler(self, signum: int = _SIGWINCH, frame: FrameType | None = None) -> None:
        """Record a terminal resize and wake the input loop.

        This runs at an arbitrary point of the program (a signal handler, or the console reader thread on Windows),
        so it only sets a flag and writes to the wake-up socket.
        :meth:`parse_input` reports the resize and drops the screen buffer in the thread that draws the screen.

        :param signum: the signal number; it is not used.
        :param frame: will always be None when the GLib event loop is being used.
        """
        self._resized = True
        self._wake_input_loop()

    def _wake_input_loop(self) -> None:
        """Make the input descriptors readable, without blocking when a wake-up is already pending."""
        with contextlib.suppress(BlockingIOError):
            self._resize_pipe_wr.send(b"R")

    @property
    def _term_input_io(self) -> SupportsFileno | None:
        if isinstance(self._term_input_file, SupportsFileno):
            return self._term_input_file
        return None

    def _input_fileno(self) -> int | None:
        """Return the fileno of the input stream, or None if it doesn't have one.

        A stream without a fileno can't participate in whatever.
        """
        if isinstance(self._term_input_file, SupportsFileno):
            return self._term_input_file.fileno()

        return None

    def _on_update_palette_entry(self, name: Hashable, *attrspecs: common.AttrSpec) -> None:
        # any drawn attribute may inherit colors from the changed entry; the next draw compares every row again
        self._pal_escape.clear()
        self._screen_buf_canvas = None

    def set_input_timeouts(
        self,
        max_wait: float | None = None,
        complete_wait: float = 0.125,
        resize_wait: float = 0.125,
    ) -> None:
        """Set the get_input timeout values.

        All values are in floating point numbers of seconds.

        :param max_wait: amount of time in seconds to wait for input when there is no input pending, wait forever if
            None
        :param complete_wait: amount of time in seconds to wait for the rest of an escape sequence cut short at the end
            of the available input, before get_input returns it decoded as it is.
            The wait never lasts past the end of *max_wait*: the sequence is then kept for the next get_input.
        :param resize_wait: amount of time in seconds to wait for more input after receiving two screen resize requests
            in a row to stop Urwid from consuming 100% cpu during a gradual window resize operation.
            The wait never lasts past the end of *max_wait*.
        """
        self.max_wait = max_wait
        self.complete_wait = complete_wait
        self.resize_wait = resize_wait

    def _is_real_terminal(self) -> bool:
        """Whether input/output are a real terminal that could answer a DECRQM probe.

        Overridden on Windows, whose input is a socket, not a descriptor `os.isatty` can inspect.
        """
        fd = self._input_fileno()
        return fd is not None and os.isatty(fd)

    @abc.abstractmethod
    def _start(  # pylint: disable=keyword-arg-before-vararg
        self,
        alternate_buffer: bool = True,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Initialize the screen and input mode.

        :param alternate_buffer: use alternate screen buffer
        :param args: not supported; an implementation raises :exc:`TypeError` when any is given.
        :param kwargs: not supported; an implementation raises :exc:`TypeError` when any is given.
        """

    @abc.abstractmethod
    def _stop(self) -> None:
        """Restore the screen."""

    def write(self, data: str) -> None:
        """Write some data to the terminal.

        You may wish to override this if you're using something other than
        regular files for input and output.
        """
        self._term_output_file.write(data)

    def flush(self) -> None:
        """Flush the output buffer.

        You may wish to override this if you're using something other than
        regular files for input and output.
        """
        self._term_output_file.flush()

    def clear(self) -> None:
        """Force the screen to be completely repainted on the next call to draw_screen()."""
        self.screen_buf = None

    def set_terminal_properties(
        self,
        colors: Literal[1, 16, 88, 256, 16777216] | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
        hyperlinks: bool | None = None,
        *,
        underline_styles: bool | None = None,
    ) -> None:
        """Set the terminal's color and attribute-rendering properties.

        :param colors: number of colors terminal supports (1, 16, 88, 256, or 2**24) or None to leave unchanged
        :param bright_is_bold: set to True if this terminal uses the bold setting to create bright colors (numbers
            8-15), set to False if this Terminal can create bright colors without bold or None to leave unchanged
        :param has_underline: set to True if this terminal can use the underline setting, False if it cannot or None to
            leave unchanged
        :param hyperlinks: set to True to draw the hyperlinks of display attributes as OSC 8 links,
            False to draw them as plain text, or None to leave unchanged.
            Off by default: no query for OSC 8 support exists, so applications that know their terminal set it.
        :param underline_styles: set to True to draw the underline styles and colors of display attributes,
            False to draw every underline single and in the text color, or None to leave unchanged.

        A property given here is the application's choice: the terminal's replies to the capability and version
        queries no longer change it.
        """
        changes: dict[str, typing.Any] = {
            "colors": colors,
            "fg_bright_is_bold": bright_is_bold,
            "has_underline": has_underline,
            "hyperlinks": hyperlinks,
            "underline_styles": underline_styles,
        }
        given = {name: value for name, value in changes.items() if value is not None}
        self._properties_set.update(given)
        self._replace_terminal_properties(given)

    def _replace_terminal_properties(self, changes: Mapping[str, typing.Any]) -> None:
        """Replace the terminal properties named in *changes*, and draw everything again when that changed any."""
        properties = dataclasses.replace(self._terminal_properties, **changes)
        if properties == self._terminal_properties:
            return
        self._terminal_properties = properties

        self.clear()
        self._pal_escape.clear()

    def _raise_terminal_properties(
        self,
        colors: _ColorCount | None,
        underline_styles: bool,
        *,
        confirmed: bool = False,
    ) -> None:
        """Change the properties the application left to detection to what a terminal reply shows the terminal draws.

        The colour count is decided by the first of these that gives one:

        1. the application, through :meth:`set_terminal_properties` or by assigning :attr:`colors`;
        2. ``NO_COLOR``, ``CLICOLOR``, ``FORCE_COLOR`` or ``CLICOLOR_FORCE`` in the environment;
        3. a reply to the rendition probe, which shows what the terminal stores, and replaces 4 and 5 either way;
        4. a capability or version reply, which only raises the count;
        5. the detection from the environment and terminfo.

        A reply turns the underline styles on unless the application set them.

        :param colors: the colour count the terminal reported, None when it reported none.
        :param underline_styles: the terminal reported that it draws the underline styles and colours.
        :param confirmed: *colors* comes from a reply to the rendition probe.
        """
        changes: dict[str, typing.Any] = {}
        if colors is not None and "colors" not in self._properties_set and not self._colors_from_environment:
            if confirmed:
                self._colors_confirmed = True
                changes["colors"] = colors
            elif not self._colors_confirmed and colors > self.colors:
                changes["colors"] = colors
        if underline_styles and "underline_styles" not in self._properties_set:
            changes["underline_styles"] = True
        self._replace_terminal_properties(changes)

    # shortcut for creating an AttrSpec with this screen object's
    # number of colors
    def AttrSpec(
        self,
        fg: str,
        bg: str,
        *,
        hyperlink: Hyperlink | str | None = None,
        underline_color: str | None = None,
    ) -> common.AttrSpec:
        """Create an :class:`AttrSpec` using this screen's number of colors.

        :param fg: the foreground color and settings, as for :class:`AttrSpec`
        :param bg: the background color, as for :class:`AttrSpec`
        :param hyperlink: the terminal hyperlink of the text, as for :class:`AttrSpec`
        :param underline_color: the color of the underline, as for :class:`AttrSpec`
        :raises AttrSpecError: *fg*, *bg* or *underline_color* is invalid or needs more colors than this screen has.
        :raises ValueError: *hyperlink* is a string that is not a valid :class:`Hyperlink` URI.
        """
        return AttrSpec(fg, bg, self._terminal_properties.colors, hyperlink=hyperlink, underline_color=underline_color)
