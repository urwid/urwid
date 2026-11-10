# Copyright (C) 2026 Urwid developers
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


"""Helpers for testing urwid widgets and applications without a terminal.

The module is not imported by :mod:`urwid`; use ``import urwid.testing``.
Every check raises :exc:`AssertionError` with a message, so the helpers work with any test framework.
"""

from __future__ import annotations

import collections
import math
import time
import typing

from urwid.canvas import CanvasCache
from urwid.display.common import BaseScreen
from urwid.event_loop import ExitMainLoop, SelectEventLoop
from urwid.util import get_encoding, is_mouse_event
from urwid.widget.constants import Sizing

if typing.TYPE_CHECKING:
    import selectors
    from collections.abc import Callable, Hashable, Iterable
    from typing import Literal

    from urwid.canvas import Canvas
    from urwid.display.common import AttrSpec, PaletteEntry
    from urwid.event_loop import EventLoop
    from urwid.widget.widget import AbstractFlowWidget, AbstractWidget

    _Size = tuple[()] | tuple[int] | tuple[int, int]
    _Input = str | tuple[str, int, int, int]
    _Runs = list[list[tuple[Hashable, str]]]

__all__ = (
    "ScriptedScreen",
    "VirtualClockEventLoop",
    "attrs_for_text",
    "check_box_sizing",
    "check_fixed_sizing",
    "check_flow_sizing",
    "check_sizing",
    "click",
    "press",
    "render_runs",
    "render_text",
    "resolve_attr",
    "resolve_runs",
)

# Position in a palette entry's (basic, mono, high_88, high_256, high_true) tuple for each number of colors.
_COLOR_INDEX: typing.Final = {1: 1, 16: 0, 88: 2, 256: 3, 2**24: 4}


def _text(canvas: Canvas, strip: bool) -> list[str]:
    if strip:
        return [line.rstrip() for line in canvas.decoded_text]
    return list(canvas.decoded_text)


def _runs(canvas: Canvas) -> _Runs:
    encoding = get_encoding()
    rows: _Runs = []
    for row in canvas.content():
        runs: list[tuple[Hashable, str]] = []
        for attr, _cs, text in row:
            decoded = text.decode(encoding)
            if runs and runs[-1][0] == attr:
                runs[-1] = (attr, runs[-1][1] + decoded)
            else:
                runs.append((attr, decoded))
        rows.append(runs)
    return rows


def render_text(widget: AbstractWidget, size: _Size, *, focus: bool = False, strip: bool = False) -> list[str]:
    """Render *widget* and return the text of each row.

    >>> from urwid import Pile, Text
    >>> render_text(Text("ab cd"), (3,))
    ['ab ', 'cd ']
    >>> render_text(Text("ab cd"), (3,), strip=True)
    ['ab', 'cd']
    >>> render_text(Pile([Text("x")]), ())
    ['x']

    :param widget: widget to render
    :param size: size to render *widget* with: ``()``, ``(cols,)`` or ``(cols, rows)``
    :param focus: whether *widget* is rendered in focus
    :param strip: remove trailing whitespace from every row
    :returns: one string per canvas row, decoded with the target encoding.
    """
    return _text(widget.render(size, focus=focus), strip)


def render_runs(widget: AbstractWidget, size: _Size, *, focus: bool = False) -> list[list[tuple[Hashable, str]]]:
    """Render *widget* and return each row as runs of display attribute and text.

    Adjacent runs with the same attribute are merged, so the result does not depend on where the canvas splits
    runs for character sets or run-length encoding.

    >>> from urwid import Text
    >>> render_runs(Text([("bold", "Hi"), "!"]), (3,))
    [[('bold', 'Hi'), (None, '!')]]

    :param widget: widget to render
    :param size: size to render *widget* with: ``()``, ``(cols,)`` or ``(cols, rows)``
    :param focus: whether *widget* is rendered in focus
    :returns: one list of ``(attr, text)`` pairs per canvas row, the text decoded with the target encoding.
    """
    return _runs(widget.render(size, focus=focus))


def attrs_for_text(
    widget: AbstractWidget,
    size: _Size,
    text: str,
    *,
    focus: bool = False,
) -> frozenset[Hashable]:
    """Render *widget* and return the display attributes of the runs that contain *text*.

    Adjacent runs with the same attribute are merged first, as in :func:`render_runs`,
    so *text* is found even where the canvas splits it.

    >>> from urwid import Text
    >>> attrs_for_text(Text([("bold", "Hi"), " there"]), (10,), "Hi")
    frozenset({'bold'})
    >>> attrs_for_text(Text([("bold", "Hi"), " there"]), (10,), "Hi there")
    frozenset()

    :param widget: widget to render
    :param size: size to render *widget* with: ``()``, ``(cols,)`` or ``(cols, rows)``
    :param text: text to look for within one run
    :param focus: whether *widget* is rendered in focus
    :returns: the attribute of every run containing *text*; empty when no single run contains it.
    """
    return frozenset(attr for row in render_runs(widget, size, focus=focus) for attr, run in row if text in run)


class _PaletteScreen(BaseScreen):
    """Screen with a palette and no terminal, for resolving display attributes."""

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Refuse to draw; this screen only resolves display attributes.

        :raises NotImplementedError: always.
        """
        raise NotImplementedError


def _palette_screen(palette: Iterable[PaletteEntry], colors: int) -> tuple[BaseScreen, int]:
    if colors not in _COLOR_INDEX:
        raise ValueError(f"colors must be one of {sorted(_COLOR_INDEX)}, got {colors!r}")
    screen = _PaletteScreen()
    screen.register_palette(palette)
    return screen, _COLOR_INDEX[colors]


def resolve_attr(attr: Hashable, palette: Iterable[PaletteEntry], *, colors: int = 256) -> AttrSpec:
    """Return the :class:`~urwid.AttrSpec` a screen with *palette* draws display attribute *attr* with.

    >>> resolve_attr("bold", [("bold", "dark red,bold", "default")], colors=16)
    AttrSpec('dark red,bold', 'default')

    :param attr: display attribute of a canvas run, such as one returned by :func:`render_runs`
    :param palette: palette entries, as passed to :class:`~urwid.MainLoop`
    :param colors: number of colors of the screen: 1, 16, 88, 256 or ``2**24``
    :returns: the attribute the screen resolves *attr* to; see :meth:`urwid.BaseScreen.resolve_attr`.
    :raises ValueError: *colors* is not one of the supported numbers of colors.
    """
    screen, index = _palette_screen(palette, colors)
    return screen.resolve_attr(attr, index)


def resolve_runs(
    runs: Iterable[Iterable[tuple[Hashable, str]]],
    palette: Iterable[PaletteEntry],
    *,
    colors: int = 256,
) -> list[list[tuple[AttrSpec, str]]]:
    """Resolve the attribute of every run returned by :func:`render_runs`, keeping the text.

    Runs are not merged again, although two attributes may resolve to the same :class:`~urwid.AttrSpec`.

    >>> from urwid import Text
    >>> runs = render_runs(Text([("bold", "Hi"), "!"]), (3,))
    >>> resolve_runs(runs, [("bold", "dark red,bold", "default")], colors=16)
    [[(AttrSpec('dark red,bold', 'default'), 'Hi'), (AttrSpec('default', 'default'), '!')]]

    :param runs: rows of ``(attr, text)`` pairs
    :param palette: palette entries, as passed to :class:`~urwid.MainLoop`
    :param colors: number of colors of the screen: 1, 16, 88, 256 or ``2**24``
    :returns: rows of ``(AttrSpec, text)`` pairs, in the shape of *runs*.
    :raises ValueError: *colors* is not one of the supported numbers of colors.
    """
    screen, index = _palette_screen(palette, colors)
    return [[(screen.resolve_attr(attr, index), text) for attr, text in row] for row in runs]


def _call(widget: AbstractWidget, size: _Size, focus: bool) -> str:
    return f"{type(widget).__name__}.render({size!r}, focus={focus!r})"


def _render_case(widget: AbstractWidget, size: _Size, focus: bool) -> Canvas:
    # A canvas cached by the test, or by the previous case for a child, would otherwise answer rows() and render().
    CanvasCache.clear()
    return widget.render(size, focus=focus)


def _check_cols(call: str, canvas: Canvas, cols: int) -> None:
    if canvas.cols() != cols:
        raise AssertionError(f"{call}: canvas cols expected {cols}, got {canvas.cols()}")


def _check_rows(call: str, canvas: Canvas, rows: int) -> None:
    if canvas.rows() != rows:
        raise AssertionError(f"{call}: canvas rows expected {rows}, got {canvas.rows()}")


def _check_cursor(call: str, canvas: Canvas) -> None:
    if (cursor := canvas.cursor) is None:
        return
    x, y = cursor
    if not (0 <= x < canvas.cols() and 0 <= y < canvas.rows()):
        raise AssertionError(
            f"{call}: cursor expected inside {canvas.cols()}x{canvas.rows()} canvas, got {cursor!r}",
        )


def check_box_sizing(widget: AbstractWidget, *, cols: int = 80, rows: int = 24) -> None:
    """Check that the box widget *widget* renders canvases of the requested size, including degenerate sizes.

    The sizes ``(cols, 0)``, ``(cols, 1)``, ``(0, rows)``, ``(1, rows)`` and ``(cols, rows)`` are rendered with
    focus off and on. Each canvas must have the requested columns and rows, and a cursor, when set, must lie
    inside it.

    .. warning::
        The check empties the canvas cache before every rendered case, so it is for tests, not for a running
        application.

    >>> from urwid import Filler, Text
    >>> check_box_sizing(Filler(Text("x")))

    :param widget: box widget to check
    :param cols: number of columns of the full size
    :param rows: number of rows of the full size
    :raises AssertionError: a canvas has the wrong size or its cursor lies outside it.
    """
    for size in ((cols, 0), (cols, 1), (0, rows), (1, rows), (cols, rows)):
        for focus in (False, True):
            call = _call(widget, size, focus)
            canvas = _render_case(widget, size, focus)
            _check_cols(call, canvas, size[0])
            _check_rows(call, canvas, size[1])
            _check_cursor(call, canvas)


def check_flow_sizing(widget: AbstractFlowWidget, *, cols: int = 80) -> None:
    """Check that the flow widget *widget* renders as many rows as its ``rows()`` reports.

    The widths 0, 1 and *cols* are rendered with focus off and on. Each canvas must have the requested columns
    and the rows ``widget.rows()`` returned before the render; in focus, its cursor must equal
    ``widget.get_cursor_coords()`` when the widget has that method; a cursor, when set, must lie inside it.

    .. warning::
        The check empties the canvas cache before every rendered case, so it is for tests, not for a running
        application.

    >>> from urwid import Edit
    >>> check_flow_sizing(Edit("> ", "abc"))

    :param widget: flow widget to check
    :param cols: number of columns of the full width
    :raises AssertionError: a canvas has the wrong size or a cursor that does not match the widget.
    """
    for width in (0, 1, cols):
        size = (width,)
        for focus in (False, True):
            call = _call(widget, size, focus)
            CanvasCache.clear()
            expected = widget.rows(size, focus)
            canvas = widget.render(size, focus=focus)
            _check_cols(call, canvas, width)
            _check_rows(call, canvas, expected)
            if focus and hasattr(widget, "get_cursor_coords"):
                coords = widget.get_cursor_coords(size)
                if canvas.cursor != coords:
                    raise AssertionError(
                        f"{call}: cursor expected {coords!r} from get_cursor_coords, got {canvas.cursor!r}"
                    )
            _check_cursor(call, canvas)


def check_fixed_sizing(widget: AbstractWidget) -> None:
    """Check that the fixed widget *widget* renders a canvas of the size its ``pack(())`` reports.

    The widget is rendered with focus off and on; a cursor, when set, must lie inside the canvas.

    .. warning::
        The check empties the canvas cache before every rendered case, so it is for tests, not for a running
        application.

    >>> from urwid import Text
    >>> check_fixed_sizing(Text("x"))

    :param widget: fixed widget to check
    :raises AssertionError: a canvas size differs from ``pack(())`` or its cursor lies outside it.
    """
    for focus in (False, True):
        call = _call(widget, (), focus)
        CanvasCache.clear()
        expected = widget.pack((), focus)
        canvas = widget.render((), focus=focus)
        if (canvas.cols(), canvas.rows()) != expected:
            raise AssertionError(
                f"{call}: canvas size expected {expected!r} from pack(()), got {(canvas.cols(), canvas.rows())!r}"
            )
        _check_cursor(call, canvas)


def check_sizing(widget: AbstractWidget, *, cols: int = 80, rows: int = 24) -> None:
    """Run the sizing check for each sizing mode in ``widget.sizing()``.

    .. warning::
        The check empties the canvas cache before every rendered case, so it is for tests, not for a running
        application.

    >>> from urwid import Pile, Text
    >>> check_sizing(Pile([Text("x")]))

    :param widget: widget to check
    :param cols: number of columns, passed to :func:`check_box_sizing` and :func:`check_flow_sizing`
    :param rows: number of rows, passed to :func:`check_box_sizing`
    :raises AssertionError: ``widget.sizing()`` is empty, or one of the checks fails.
    """
    modes = widget.sizing()
    if not modes:
        raise AssertionError(f"{type(widget).__name__}.sizing() is empty")
    for mode in sorted(modes):
        match mode:
            case Sizing.BOX:
                check_box_sizing(widget, cols=cols, rows=rows)
            case Sizing.FLOW:
                check_flow_sizing(typing.cast("AbstractFlowWidget", widget), cols=cols)
            case Sizing.FIXED:
                check_fixed_sizing(widget)
            case _:
                typing.assert_never(mode)


def press(widget: AbstractWidget, size: _Size, *keys: str) -> list[str]:
    """Send *keys* to ``widget.keypress()`` in order and return the keys it did not handle.

    The returned key is collected, not the sent one, since a widget may translate a key.

    >>> from urwid import Edit
    >>> edit = Edit("> ")
    >>> press(edit, (10,), "a", "b", "esc")
    ['esc']
    >>> edit.edit_text
    'ab'

    :param widget: widget to send the keys to
    :param size: size passed to ``keypress()``
    :param keys: key names, such as ``"a"`` or ``"enter"``
    :returns: the keys ``keypress()`` returned, in order.
    """
    return [returned for key in keys if (returned := widget.keypress(size, key)) is not None]


def click(
    widget: AbstractWidget,
    size: _Size,
    col: int,
    row: int,
    *,
    button: int = 1,
    event: str = "mouse press",
    focus: bool = True,
) -> bool:
    """Send one mouse event to ``widget.mouse_event()`` and return whether it was handled.

    >>> from urwid import Button, MouseButton
    >>> click(Button("OK"), (10,), 1, 0)
    True
    >>> click(Button("OK"), (10,), 1, 0, button=MouseButton.RIGHT)
    False

    :param widget: widget to send the event to
    :param size: size passed to ``mouse_event()``
    :param col: column of the event, relative to the widget
    :param row: row of the event, relative to the widget
    :param button: mouse button number, see :class:`~urwid.MouseButton`
    :param event: event name, such as ``"mouse press"`` or ``"mouse release"``
    :param focus: whether *widget* is in focus
    :returns: ``True`` when ``mouse_event()`` returned a true value.
    """
    return bool(widget.mouse_event(size, event, button, col, row, focus))


class ScriptedScreen(BaseScreen):
    """Screen without a terminal that records what is drawn and feeds scripted input to :class:`~urwid.MainLoop`.

    ``MainLoop(widget, palette, screen=ScriptedScreen(...))`` works with :meth:`~urwid.MainLoop.run`, which
    feeds one batch of *inputs* after every redraw and stops with :exc:`~urwid.ExitMainLoop` once they are used up,
    and with :meth:`~urwid.MainLoop.process_input` plus :meth:`~urwid.MainLoop.draw_screen` called by hand.

    A draw whose size, content (text and attributes) and cursor equal those of the last recorded frame is not
    recorded again, so :attr:`canvases` is the same sequence of distinct screens under every event loop, while the
    number of draws differs between them. Assert the frames and :attr:`last_text`, not a count of draws.

    The input batches are consumed, so one screen scripts one :meth:`~urwid.MainLoop.run`. Alarms still pending
    after the last batch never fire.

    >>> from urwid import Edit, Filler, MainLoop
    >>> screen = ScriptedScreen(size=(6, 1), inputs=[["a", "b"], ["backspace"]])
    >>> MainLoop(Filler(Edit("> ")), screen=screen).run()
    >>> [frame.decoded_text for frame in screen.canvases]
    [('>     ',), ('> ab  ',), ('> a   ',)]
    >>> screen.last_text
    ['> a   ']
    """

    def __init__(
        self,
        *,
        size: tuple[int, int] = (80, 24),
        inputs: Iterable[Iterable[_Input]] = (),
    ) -> None:
        """Create an unstarted screen.

        :param size: ``(cols, rows)`` returned by :meth:`get_cols_rows`; assign :attr:`size` to resize, then
            script a ``"window resize"`` key
        :param inputs: batches of keys and mouse event tuples, one batch returned by each :meth:`get_input`
        :raises TypeError: a batch is not a sequence of keys and mouse event tuples.
        """
        batches: list[list[_Input]] = []
        for batch in inputs:
            items = None if isinstance(batch, (str, bytes)) or is_mouse_event(batch) else list(batch)
            if items is None or not all(isinstance(item, str) or is_mouse_event(item) for item in items):
                raise TypeError(f"each input batch must be a sequence of keys and mouse event tuples, got {batch!r}")
            batches.append(items)
        super().__init__()
        #: ``(cols, rows)`` returned by :meth:`get_cols_rows`
        self.size = size
        #: distinct frames drawn, oldest first; ``canvases[-1]`` is the screen shown last
        self.canvases: list[Canvas] = []
        #: number of :meth:`draw_screen` calls, recorded or not
        self.draw_count = 0
        self._inputs = collections.deque(batches)
        self._frame: tuple[tuple[int, int], list[typing.Any], tuple[int, int] | None] | None = None
        self._event_loop: EventLoop | None = None
        self._callback: Callable[[list[_Input], list[int]], typing.Any] | None = None
        self._feed_handle: typing.Any = None

    @property
    def last_text(self) -> list[str]:
        """Return the text of each row of the frame drawn last.

        :raises IndexError: nothing has been drawn yet.
        """
        return _text(self.canvases[-1], strip=False)

    def get_cols_rows(self) -> tuple[int, int]:
        """Return :attr:`size`."""
        return self.size

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Record *canvas* unless it shows the same frame as the last one, then schedule the next input batch.

        :param size: ``(cols, rows)`` the canvas was rendered for
        :param canvas: canvas to show
        """
        self.draw_count += 1
        frame = (size, list(canvas.content()), canvas.cursor)
        if frame != self._frame:
            self._frame = frame
            self.canvases.append(canvas)
        if self._event_loop is not None and self._feed_handle is None:
            self._feed_handle = self._event_loop.alarm(0, self._feed)

    def _feed(self) -> None:
        self._feed_handle = None
        if self._callback is not None:
            self._callback(*self.get_input(True))

    @typing.overload
    def get_input(self, raw_keys: Literal[False] = ...) -> list[_Input]: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[list[_Input], list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> list[_Input] | tuple[list[_Input], list[int]]:
        """Return the next input batch.

        :param raw_keys: also return the raw key codes, which are always empty
        :returns: the batch, or ``(batch, [])`` when *raw_keys* is true.
        :raises ExitMainLoop: the scripted batches are used up.
        """
        if not self._inputs:
            raise ExitMainLoop
        batch = self._inputs.popleft()
        if raw_keys:
            return batch, []
        return batch

    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[list[_Input], list[int]], typing.Any],
    ) -> None:
        """Feed the input batches to *callback* through alarms of *event_loop*, one after every draw.

        :param event_loop: event loop to schedule the batches on
        :param callback: function taking the keys and the raw key codes of one batch
        """
        self._event_loop = event_loop
        self._callback = callback

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """Cancel a pending input batch and forget the event loop.

        :param event_loop: event loop passed to :meth:`hook_event_loop`
        """
        if self._feed_handle is not None:
            event_loop.remove_alarm(self._feed_handle)
            self._feed_handle = None
        self._event_loop = None
        self._callback = None


class VirtualClockEventLoop(SelectEventLoop):
    """Event loop whose alarms fire on a clock of its own, which jumps to the next alarm instead of waiting for it.

    Pass it as ``MainLoop(..., event_loop=VirtualClockEventLoop())`` to test a widget or an application that sets
    alarms, such as :class:`~urwid.Notifications`, without real delays.
    :meth:`~urwid.MainLoop.set_alarm_in` schedules against this clock.
    :meth:`~urwid.MainLoop.set_alarm_at` still takes a :func:`time.time` value, and only its offset from now counts.
    Alarms due together fire in the order they were set,
    and the loop enters idle, drawing the screen, as :class:`~urwid.SelectEventLoop` does.

    Watched files are polled without waiting, so input, :meth:`~urwid.MainLoop.watch_pipe` and
    :meth:`~urwid.MainLoop.call_from_thread` work as on the select loop.
    The clock moves only while no watched file is readable, so a file that stays readable keeps later alarms from
    coming due until *timeout* runs out.
    A loop with nothing left to do but watch files waits for them in real time, up to *timeout*.
    :meth:`run_until_idle` runs every pending alarm and readable file instead, and returns once none is left.

    The clock is the loop's own: code that reads :func:`time.monotonic` itself does not see it move.

    >>> from urwid import MainLoop, Notifications, SolidFill
    >>> event_loop = VirtualClockEventLoop()
    >>> loop = MainLoop(SolidFill(), screen=ScriptedScreen(), event_loop=event_loop)
    >>> notifications = Notifications(loop=loop, timeout=5)
    >>> _ = notifications.notify("saved")
    >>> event_loop.advance(4.9)
    >>> len(notifications.notifications), event_loop.now
    (1, 4.9)
    >>> event_loop.advance(0.1)
    >>> len(notifications.notifications)
    0
    """

    def __init__(self, *, timeout: float = 5.0) -> None:
        """Create a loop whose clock reads 0.

        :param timeout: seconds of real time a :meth:`run`, an :meth:`advance` or a :meth:`run_until_idle` may take
        """
        super().__init__()
        self._timeout = timeout
        self._now = 0.0
        self._deadline: float | None = None
        # Clock time an advance() stops at, math.inf for run_until_idle(); None while run() runs.
        self._target: float | None = None
        self._reached = False
        # Seconds of real time spent watching files before the clock jumps to the next alarm.
        self._pause = 0.0

    @property
    def now(self) -> float:
        """Return the time of the loop's clock, in seconds since the loop was created."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock *seconds* ahead, firing every alarm that comes due on the way.

        Alarms fire in the order they come due, each with the clock at its due time,
        and the loop enters idle before the clock moves on.
        Readable watched files are served on the way, but the loop does not wait for one.
        Exceptions raised by the callbacks, :exc:`~urwid.ExitMainLoop` included, reach the caller.

        :param seconds: how far to move the clock; 0 fires the alarms already due
        :raises ValueError: *seconds* is negative.
        :raises RuntimeError: called from a callback of an :meth:`advance`, a :meth:`run` or a
            :meth:`run_until_idle` of this loop.
        :raises TimeoutError: the alarms still came due after *timeout* seconds of real time.
        """
        if seconds < 0:
            raise ValueError(f"seconds must not be negative, got {seconds!r}")
        target = self._now + seconds
        self._run_to(target, pause=0.0)
        self._now = target

    def run_until_idle(self, *, pause: float = 0.0) -> None:
        """Fire every pending alarm and serve every readable watched file, until none is left.

        The clock jumps from alarm to alarm, as in :meth:`advance`, and stops at the last alarm that fired.
        Alarms set by the callbacks fire in the same call.
        The loop enters idle before it returns, so a started :class:`~urwid.MainLoop` has drawn the screen.
        A watched file that is not readable is waited for only during the pauses.
        Exceptions raised by the callbacks, :exc:`~urwid.ExitMainLoop` included, reach the caller.

        >>> event_loop = VirtualClockEventLoop()
        >>> _ = event_loop.alarm(3, lambda: event_loop.alarm(2, lambda: None))
        >>> event_loop.run_until_idle()
        >>> event_loop.now
        5.0

        :param pause: seconds of real time to watch the files before each jump of the clock to the next alarm,
            so a worker thread polled by an alarm can hand back its result, for example through
            :meth:`~urwid.MainLoop.call_from_thread`; the pauses count toward *timeout*
        :raises ValueError: *pause* is negative or not finite.
        :raises RuntimeError: called from a callback of an :meth:`advance`, a :meth:`run` or a
            :meth:`run_until_idle` of this loop.
        :raises TimeoutError: alarms were still pending, or a file still readable, after *timeout* seconds of
            real time.
        """
        if not (math.isfinite(pause) and pause >= 0):
            raise ValueError(f"pause must be finite and not negative, got {pause!r}")
        self._run_to(math.inf, pause=pause)

    def _run_to(self, target: float, *, pause: float) -> None:
        """Run the loop until the next alarm is due after *target* and no file is readable.

        :param target: clock time to stop at; :data:`math.inf` runs until no alarm is pending
        :param pause: seconds of real time to watch the files before the clock jumps to the next alarm
        :raises RuntimeError: an :meth:`advance`, a :meth:`run` or a :meth:`run_until_idle` of this loop is running.
        :raises TimeoutError: the loop still ran after *timeout* seconds of real time.
        """
        self._check_not_running()
        self._target = target
        self._pause = pause
        self._reached = False
        self._deadline = time.monotonic() + self._timeout
        try:
            while not self._reached and (self._alarms or self._did_something or self._watch_files):
                self._loop()
        finally:
            self._target = None
            self._pause = 0.0
            self._deadline = None

    def run(self) -> None:
        """Run the loop until a callback raises :exc:`~urwid.ExitMainLoop`.

        :raises TimeoutError: the loop still ran after *timeout* seconds of real time.
        :raises RuntimeError: no alarm is pending and no file is watched, so the loop would wait forever.
            Also when called from a callback of an :meth:`advance`, a :meth:`run` or a :meth:`run_until_idle` of
            this loop.
        """
        self._check_not_running()
        self._deadline = time.monotonic() + self._timeout
        try:
            super().run()
        finally:
            self._deadline = None

    def _check_not_running(self) -> None:
        """Refuse to start a run inside another one, which would overwrite its target and deadline.

        :raises RuntimeError: an :meth:`advance`, a :meth:`run` or a :meth:`run_until_idle` of this loop is running.
        """
        # Each of them sets the deadline for its whole duration, and only they set it.
        if self._deadline is not None:
            raise RuntimeError("advance(), run() and run_until_idle() cannot be called while the loop runs")

    def _loop(self) -> None:
        """Run one iteration of the loop, unless it has run out of real time or has nothing to wait for."""
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError(f"the event loop still ran after {self._timeout} seconds")
        if not (self._alarms or self._did_something or self._watch_files):
            raise RuntimeError("no alarm is pending and no file is watched, so the event loop would wait forever")
        super()._loop()

    def _clock(self) -> float:
        """Return the time of the loop's clock."""
        return self._now

    def _wait(self, selector: selectors.BaseSelector, timeout: float | None) -> list[selectors.SelectorKey]:
        """Return the readable watched files.

        When none is readable, the clock moves to the next alarm.
        A :meth:`run_until_idle` with a pause first watches the files, or sleeps when none is watched,
        for that pause or until its deadline.
        An :meth:`advance` or a :meth:`run_until_idle` with no alarm due at or before its target ends instead.
        A :meth:`run` with no alarm pending waits for a file in real time, up to its deadline.

        :param selector: selector registering every watched file
        :param timeout: seconds until the next alarm is due; ``None`` when none is pending
        :returns: the keys of the readable files.
        :raises TimeoutError: :meth:`run` waited for a watched file until the real-time deadline.
        """
        if self._watch_files and (ready := [event for event, _ in selector.select(0)]):
            return ready
        if timeout == 0:
            return []
        # A positive timeout always runs to the first alarm.
        due = None if timeout is None else self._alarms[0][0]
        if self._target is not None and (due is None or due > self._target):
            # advance() sets the clock to its target once the loop has stopped.
            self._reached = True
            return []
        if due is not None:
            if self._pause and self._deadline is not None:
                pause = min(self._pause, max(0.0, self._deadline - time.monotonic()))
                if not self._watch_files:
                    time.sleep(pause)
                elif ready := [event for event, _ in selector.select(pause)]:
                    return ready
            self._now = due
            return []
        remaining = 0.0 if self._deadline is None else max(0.0, self._deadline - time.monotonic())
        if self._watch_files and (ready := [event for event, _ in selector.select(remaining)]):
            return ready
        raise TimeoutError(f"no watched file became readable within {self._timeout} seconds")
