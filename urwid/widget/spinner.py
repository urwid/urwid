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


"""Spinner: an activity indicator for work without a known total."""

from __future__ import annotations

import enum
import math
import time
import typing
from collections.abc import Sequence

from urwid.split_repr import remove_defaults
from urwid.str_util import calc_width
from urwid.util import decompose_tagmarkup

from .constants import Align, WrapMode
from .text import Text

if typing.TYPE_CHECKING:
    from urwid.event_loop import MainLoop
    from urwid.util import _TagMarkup

__all__ = ("Spinner", "SpinnerFrames")


class SpinnerFrames(enum.Enum):
    """Common frame sets for :class:`Spinner`, also reachable as :attr:`Spinner.Frames`.

    The frames of each member have one width.
    On a terminal without UTF-8:

    - :attr:`LINE` and :attr:`DOTS` are ASCII and are drawn as they are.
    - Every other member is drawn as its :func:`~urwid.set_ascii_fallbacks` replacement, or as ``?`` without one.

    .. note::
        The default terminal fonts of GNOME, KDE Plasma and Xfce on Ubuntu, Fedora and Arch,
        and of Windows Terminal, show every member.
        The default fonts of the Linux virtual console are:

        - Ubuntu: Fixed 8x16.
        - Fedora and openSUSE: eurlatgr.
        - Arch: the built-in 8x16 font of the kernel.

        The default fonts of the Linux virtual console and of the classic Windows console
        show none of the non-ASCII members,
        so use :attr:`LINE` or :attr:`DOTS` there unless the console font has wider coverage.
    """

    LINE = ("-", "\\", "|", "/")
    DOTS = (".  ", ".. ", "...", "   ")
    BRAILLE = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    ARC = ("◜", "◠", "◝", "◞", "◡", "◟")
    CIRCLE_QUARTERS = ("◴", "◷", "◶", "◵")


class Spinner(Text):
    r"""A text widget showing its frames in turn while some work runs.

    :meth:`start` shows the first frame and sets an alarm that shows the next one every :attr:`interval` seconds.
    The frame is chosen from the time elapsed since :meth:`start`,
    so a late alarm skips frames instead of slowing the spinner down.
    :meth:`stop` removes the alarm and shows the :attr:`idle` text, which is also shown before the first frame.
    :meth:`step` shows the next frame by hand, for an application that drives the spinner from its own tick.

    :meth:`start`, :meth:`step` and :meth:`stop` replace the text,
    so put a label in its own :class:`Text` next to the spinner, for example in a :class:`Columns`.
    Every frame and the default idle text have one width, so a ``"pack"`` cell keeps its width.

    The alarm is set on :attr:`loop`, or, without one, on the :class:`MainLoop` running when :meth:`start` is called
    (see :func:`~urwid.get_running_loop`).
    The pending alarm keeps a running spinner alive: stop a spinner that leaves the screen.

    .. important::
        Call every method from the thread running the loop, like every other widget change.
        Another thread hands the call over with :meth:`MainLoop.call_from_thread`.

    >>> spinner = Spinner(Spinner.Frames.LINE)
    >>> spinner.render((3,)).text
    [b'   ']
    >>> spinner.step()
    >>> spinner.render((3,)).text
    [b'-  ']
    >>> spinner.step()
    >>> spinner.render((3,)).text
    [b'\\  ']
    >>> spinner.stop()
    >>> spinner.render((3,)).text
    [b'   ']
    """

    Frames: typing.ClassVar[type[SpinnerFrames]] = SpinnerFrames

    def __init__(
        self,
        frames: SpinnerFrames | Sequence[str] = SpinnerFrames.LINE,
        *,
        interval: float = 0.1,
        idle: _TagMarkup | None = None,
        loop: MainLoop | None = None,
        align: typing.Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: typing.Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
    ) -> None:
        """Build a stopped spinner showing the idle text.

        :param frames: frames shown in turn,
            a :class:`Spinner.Frames <urwid.widget.spinner.SpinnerFrames>` member or a sequence of strings.
            Frames narrower than the widest are padded with spaces on the right.
        :param interval: seconds each frame is shown while running, see :attr:`interval`.
        :param idle: text markup shown while stopped, see :attr:`idle`.
        :param loop: loop the alarm is set on.
            ``None`` uses the loop running at each :meth:`start`.
        :param align: alignment of the text.
        :param wrap: wrap mode of the text.
        :raises TypeError: *frames* is not a :class:`Spinner.Frames <urwid.widget.spinner.SpinnerFrames>` member
            or a sequence of strings, or *interval* is not a number.
        :raises ValueError: *frames* is empty, a frame is not printable or is zero columns wide,
            or *interval* is not finite and > 0.
        :raises TextError: *align* or *wrap* is not supported by the text layout.
        :raises TagMarkupException: *idle* is not valid text markup.
        """
        self._frames = self._valid_frames(frames)
        self._frames_arg: SpinnerFrames | tuple[str, ...] = (
            frames if isinstance(frames, SpinnerFrames) else self._frames
        )
        self._interval = self._valid_interval(interval)
        self._idle = idle
        self._loop = loop
        # The frame showing, or None while the idle text shows.
        self._index: int | None = None
        # Frames added to the count of intervals elapsed since the start: by step(), and when the interval changes.
        self._offset = 0
        # (start time, loop, alarm handle) while running: the alarm is pending exactly while this is set.
        self._run: tuple[float, MainLoop, typing.Any] | None = None
        super().__init__(self._idle_markup(), align, wrap)

    @staticmethod
    def _valid_frames(frames: SpinnerFrames | Sequence[str]) -> tuple[str, ...]:
        """Return the frames as a tuple, each padded with spaces to the width of the widest.

        :raises TypeError: *frames* is not a :class:`Spinner.Frames <urwid.widget.spinner.SpinnerFrames>` member
            or a sequence of strings.
        :raises ValueError: *frames* is empty, or a frame is not printable or is zero columns wide.
        """
        if isinstance(frames, SpinnerFrames):
            sequence: Sequence[str] = frames.value
        elif (
            not isinstance(frames, Sequence)
            or isinstance(frames, (str, bytes))
            or not all(isinstance(frame, str) for frame in frames)
        ):
            raise TypeError(f"frames must be a SpinnerFrames member or a sequence of str, not {frames!r}")
        else:
            sequence = frames
        if not sequence:
            raise ValueError("frames must hold at least one frame")
        widths = []
        for frame in sequence:
            width = calc_width(frame, 0, len(frame))
            # isprintable() rejects tabs and newlines, which the text layout draws wider than calc_width counts.
            if not frame.isprintable() or width < 1:
                raise ValueError(f"each frame must be printable and at least one column wide, not {frame!r}")
            widths.append(width)
        widest = max(widths)
        return tuple(frame + " " * (widest - width) for frame, width in zip(sequence, widths, strict=True))

    @staticmethod
    def _valid_interval(interval: float) -> float:
        """Return *interval* unchanged.

        :raises TypeError: it is not an int or a float.
        :raises ValueError: it is not finite and > 0, or it is an int too large for a float.
        """
        if not isinstance(interval, (int, float)) or isinstance(interval, bool):
            raise TypeError(f"interval must be a number of seconds, not {interval!r}")
        try:
            finite = math.isfinite(interval)
        except OverflowError as exc:
            raise ValueError(f"interval must be finite and > 0, not {interval!r}") from exc
        if not finite or interval <= 0:
            raise ValueError(f"interval must be finite and > 0, not {interval!r}")
        return interval

    def _repr_attrs(self) -> dict[str, typing.Any]:
        """Return the constructor arguments that differ from their defaults, for the repr."""
        attrs = {
            **super()._repr_attrs(),
            "frames": self._frames_arg,
            "interval": self._interval,
            "idle": self._idle,
            "loop": self._loop,
        }
        return remove_defaults(attrs, Spinner.__init__)

    def _idle_markup(self) -> _TagMarkup:
        """Return the idle text, or spaces as wide as a frame without one."""
        if self._idle is None:
            return " " * calc_width(self._frames[0], 0, len(self._frames[0]))
        return self._idle

    def _show(self, index: int | None) -> None:
        """Show the frame at *index*, or the idle text for ``None``."""
        self._index = index
        self.set_text(self._idle_markup() if index is None else self._frames[index])

    def _reset(self) -> None:
        """Forget the run, without touching its alarm, and show the idle text."""
        self._run = None
        self._offset = 0
        self._show(None)

    @property
    def running(self) -> bool:
        """Whether the frames are changing on an alarm, between :meth:`start` and :meth:`stop`."""
        return self._run is not None

    @property
    def frames(self) -> tuple[str, ...]:
        """The frames shown in turn, each padded to one width."""
        return self._frames

    @property
    def interval(self) -> float:
        """Seconds each frame is shown while running.

        A new value applies at once: a running spinner keeps the frame showing
        and shows the next one after the new interval.

        :raises TypeError: the new value is not a number.
        :raises ValueError: the new value is not finite and > 0.
        :raises Exception: the loop failed to set the new alarm; the spinner is then stopped.
        """
        return self._interval

    @interval.setter
    def interval(self, interval: float) -> None:
        self._interval = self._valid_interval(interval)
        if self._run is None:
            return
        if self._index is None:
            raise AssertionError("a running Spinner always shows a frame")
        # Re-based on the frame showing rather than on the clock, which is ahead of it while an alarm is overdue.
        offset = self._index
        _started, loop, handle = self._run
        loop.remove_alarm(handle)
        # Stopped and idle until the new alarm is set, so a failure to set it leaves a stopped spinner.
        self._reset()
        started = time.monotonic()
        self._run = (started, loop, loop.set_alarm_in(self._interval, self._tick))
        self._offset = offset
        self._show(offset)

    @property
    def idle(self) -> _TagMarkup | None:
        """Text markup shown while stopped, or ``None`` for spaces as wide as a frame.

        A new value shows at once while the idle text shows, and otherwise from the next :meth:`stop`.

        :raises TagMarkupException: the new value is not valid text markup.
        """
        return self._idle

    @idle.setter
    def idle(self, idle: _TagMarkup | None) -> None:
        if idle is not None:
            decompose_tagmarkup(idle)
        self._idle = idle
        if self._index is None:
            self._show(None)

    @property
    def loop(self) -> MainLoop | None:
        """Loop the alarm is set on, or ``None`` to use the loop running at each :meth:`start`."""
        return self._loop

    def start(self) -> None:
        """Show frames in turn on an alarm, until :meth:`stop`.

        A spinner started from the idle text shows the first frame.
        One started after :meth:`step` goes on from the frame showing.
        A running spinner is left as it is.
        A call that raises leaves the spinner as it was.

        :raises RuntimeError: there is no :attr:`loop` and no loop is running.
            Pass ``loop=`` to start a spinner before the loop runs.
        """
        if self._run is not None:
            return
        loop = self._loop
        if loop is None:
            # urwid.event_loop imports urwid.widget, so it cannot be imported at module scope here
            from urwid.event_loop import get_running_loop

            loop = get_running_loop()
        started = time.monotonic()
        handle = loop.set_alarm_in(self._interval, self._tick)
        self._run = (started, loop, handle)
        self._offset = 0 if self._index is None else self._index
        self._show(self._offset)

    def step(self) -> None:
        """Show the next frame.

        On a stopped spinner the first call shows the first frame.
        On a running one the frames after it keep the shift by one.
        """
        if self._run is None:
            self._show(0 if self._index is None else (self._index + 1) % len(self._frames))
            return
        self._offset += 1
        started = self._run[0]
        self._show((int((time.monotonic() - started) / self._interval) + self._offset) % len(self._frames))

    def stop(self) -> None:
        """Remove the alarm and show the idle text.

        A later :meth:`start` begins at the first frame.
        A stopped spinner only shows the idle text again.
        """
        if self._run is not None:
            _started, loop, handle = self._run
            loop.remove_alarm(handle)
        self._reset()

    def _tick(self, _loop: MainLoop, _user_data: None) -> None:
        """Show the frame due now and set the alarm for the next one.

        :raises Exception: the loop failed to set the next alarm; the spinner is then stopped.
        """
        if self._run is None:
            raise AssertionError("a Spinner alarm fired after stop() removed it")
        started, loop, _handle = self._run
        now = time.monotonic()
        count = int((now - started) / self._interval)
        self._show((count + self._offset) % len(self._frames))
        try:
            handle = loop.set_alarm_in(max(0.0, started + (count + 1) * self._interval - now), self._tick)
        except BaseException:
            self._reset()
            raise
        self._run = (started, loop, handle)
