"""Tests for :class:`urwid.Spinner`."""

from __future__ import annotations

import contextvars
import itertools
import math
import typing
import unittest
import unittest.mock
import weakref

import urwid
from tests.util import collect_and_count_alive, external_loop
from urwid.testing import check_sizing, render_text

LINE = ("-", "\\", "|", "/")
# Exact in binary floating point, so the frame boundaries computed from the clock below are exact too.
INTERVAL = 0.5
START = 100.0


def mock_loop() -> unittest.mock.Mock:
    """Return a mock ``MainLoop`` whose ``set_alarm_in`` returns the handles ``"alarm 0"``, ``"alarm 1"``, ..."""
    loop = unittest.mock.Mock(spec=urwid.MainLoop)
    loop.set_alarm_in.side_effect = (f"alarm {n}" for n in itertools.count())
    return loop


def fire(loop: unittest.mock.Mock, call: int = -1) -> None:
    """Call the alarm callback of the *call*-th ``set_alarm_in`` call of *loop*, as the loop does when it fires."""
    _seconds, callback = loop.set_alarm_in.call_args_list[call].args
    callback(loop, None)


class FakeTime:
    """Stand-in for the ``time`` module, whose ``monotonic()`` returns :attr:`now`."""

    def __init__(self) -> None:
        """Start the clock at :data:`START`."""
        self.now = START

    def monotonic(self) -> float:
        """Return :attr:`now`."""
        return self.now


class ClockTestCase(unittest.TestCase):
    """A test case whose spinners read :attr:`clock` instead of the real monotonic clock."""

    def setUp(self) -> None:
        """Patch the ``time`` module of the spinner with a :class:`FakeTime`."""
        self.clock = FakeTime()
        patcher = unittest.mock.patch("urwid.widget.spinner.time", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def at(self, intervals: float) -> None:
        """Move the clock to *intervals* intervals after :data:`START`."""
        self.clock.now = START + intervals * INTERVAL


class SpinnerConstructionTest(unittest.TestCase):
    """Building a ``Spinner`` and validating its arguments."""

    def test_defaults(self) -> None:
        """A new spinner is stopped, shows a blank frame-wide idle text, and its repr names no argument."""
        spinner = urwid.Spinner()
        self.assertFalse(spinner.running)
        self.assertEqual(LINE, spinner.frames)
        self.assertEqual(0.1, spinner.interval)
        self.assertIsNone(spinner.idle)
        self.assertIsNone(spinner.loop)
        self.assertEqual(" ", spinner.text)
        self.assertEqual("<Spinner fixed/flow widget ' '>", repr(spinner))

    def test_repr_with_options(self) -> None:
        """The repr names each argument that differs from its default."""
        loop = mock_loop()
        for kwargs, expected in (
            ({"frames": urwid.SpinnerFrames.ARC}, "frames=<SpinnerFrames.ARC: "),
            ({"frames": ["a", "bb"]}, "frames=('a ', 'bb')"),
            ({"interval": 0.25}, "interval=0.25"),
            ({"idle": "done"}, "idle='done'"),
            ({"loop": loop}, "loop=<Mock spec='MainLoop'"),
            ({"align": "right"}, "align='right'"),
            ({"wrap": "clip"}, "wrap='clip'"),
        ):
            with self.subTest(**{name: str(value) for name, value in kwargs.items()}):
                self.assertIn(expected, repr(urwid.Spinner(**kwargs)))

    def test_presets(self) -> None:
        """Every preset is accepted, and its frames are one column-width each."""
        for member in urwid.SpinnerFrames:
            with self.subTest(member.name):
                spinner = urwid.Spinner(member)
                self.assertEqual(member.value, spinner.frames)
                widths = {urwid.str_util.calc_width(frame, 0, len(frame)) for frame in spinner.frames}
                self.assertEqual(1, len(widths))

    def test_frames_padded(self) -> None:
        """Frames narrower than the widest are padded with spaces on the right; a tuple of str is taken too."""
        self.assertEqual(("a  ", "bbb", "c  "), urwid.Spinner(["a", "bbb", "c"]).frames)
        self.assertEqual(("x", "y"), urwid.Spinner(("x", "y")).frames)

    def test_bad_frames(self) -> None:
        """Frames that are not a sequence of printable, non-empty str are rejected."""
        for label, frames, error in (
            ("empty str", "", TypeError),
            ("bytes", b"-\\|/", TypeError),
            ("bare str", "-\\|/", TypeError),
            ("non-str frame", ["-", 1], TypeError),
            ("int", 5, TypeError),
            ("iterator", iter(["-"]), TypeError),
            ("set", {"-", "|"}, TypeError),
            ("empty list", [], ValueError),
            ("empty frame", ["-", ""], ValueError),
            ("newline", ["a\nb"], ValueError),
            ("tab", ["a\tb", "xx"], ValueError),
            ("combining only", ["́"], ValueError),
        ):
            with self.subTest(label), self.assertRaises(error):
                urwid.Spinner(frames)  # type: ignore[arg-type]

    def test_bad_interval(self) -> None:
        """An interval that is not a finite number > 0 is rejected, at construction and by the setter."""
        spinner = urwid.Spinner()
        for value, error in (
            (0, ValueError),
            (-1, ValueError),
            (math.nan, ValueError),
            (math.inf, ValueError),
            (10**400, ValueError),
            (True, TypeError),
            ("0.1", TypeError),
        ):
            with self.subTest(repr(value)):
                with self.assertRaises(error):
                    urwid.Spinner(interval=value)  # type: ignore[arg-type]
                with self.assertRaises(error):
                    spinner.interval = value  # type: ignore[assignment]
                self.assertEqual(0.1, spinner.interval)

    def test_bad_idle(self) -> None:
        """Bad idle markup raises at construction and in the setter, which then keeps the old value."""
        with self.assertRaises(urwid.TagMarkupException):
            urwid.Spinner(idle=1)  # type: ignore[arg-type]
        spinner = urwid.Spinner(idle="ok")
        with self.assertRaises(urwid.TagMarkupException):
            spinner.idle = 1  # type: ignore[assignment]
        self.assertEqual("ok", spinner.idle)
        self.assertEqual("ok", spinner.text)


class SpinnerRenderTest(unittest.TestCase):
    """What a spinner draws, without a loop."""

    def test_idle_width(self) -> None:
        """The default idle text is as wide as a frame, and pack() is the same for each frame and for idle."""
        spinner = urwid.Spinner(urwid.SpinnerFrames.DOTS)
        self.assertEqual(["   "], render_text(spinner, ()))
        packs = {spinner.pack(())}
        for _ in spinner.frames:
            spinner.step()
            packs.add(spinner.pack(()))
        self.assertEqual({(3, 1)}, packs)

    def test_idle_text(self) -> None:
        """A new idle text shows at once while the idle text shows, and after stop() on a stepped spinner."""
        spinner = urwid.Spinner(idle="done")
        self.assertEqual(["done"], render_text(spinner, ()))
        spinner.idle = None
        self.assertEqual([" "], render_text(spinner, ()))
        spinner.idle = ("bold", "ok")
        self.assertEqual(["ok"], render_text(spinner, ()))
        spinner.step()
        spinner.idle = "zz"
        self.assertEqual(["-"], render_text(spinner, ()))
        spinner.stop()
        self.assertEqual(["zz"], render_text(spinner, ()))

    def test_step_cycles(self) -> None:
        """The first step from idle shows the first frame, later ones go on and wrap around."""
        spinner = urwid.Spinner()
        shown = []
        for _ in range(6):
            spinner.step()
            shown.append(spinner.text)
        self.assertEqual(["-", "\\", "|", "/", "-", "\\"], shown)
        self.assertFalse(spinner.running)

    def test_stop_shows_idle(self) -> None:
        """stop() on a stopped spinner driven by step() shows the idle text, and the next step() the first frame."""
        spinner = urwid.Spinner()
        spinner.step()
        spinner.step()
        spinner.stop()
        self.assertEqual(" ", spinner.text)
        spinner.step()
        self.assertEqual("-", spinner.text)

    def test_sizing(self) -> None:
        """A spinner is a flow and fixed widget, idle and showing a frame."""
        spinner = urwid.Spinner()
        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), spinner.sizing())
        check_sizing(spinner)
        spinner.step()
        check_sizing(spinner)


class SpinnerAlarmTest(ClockTestCase):
    """Frames driven by the alarm of a mock loop."""

    def test_start(self) -> None:
        """start() sets one alarm one interval ahead with the tick, and shows the first frame; a second does nothing."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        spinner.start()
        loop.set_alarm_in.assert_called_once_with(INTERVAL, spinner._tick)
        self.assertTrue(spinner.running)
        self.assertEqual("-", spinner.text)

    def test_start_after_step(self) -> None:
        """start() after manual steps keeps the frame showing and goes on from it on the next tick."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.step()
        spinner.step()
        spinner.start()
        self.assertEqual("\\", spinner.text)
        self.at(1)
        fire(loop)
        self.assertEqual("|", spinner.text)

    def test_ticks_follow_the_clock(self) -> None:
        """Each tick shows the frame for the time elapsed, skips missed frames, and re-arms for the next boundary."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        for intervals, frame, delay in ((1, "\\", 1), (2.25, "|", 0.75), (7, "/", 1), (9.5, "\\", 0.5)):
            with self.subTest(intervals=intervals):
                self.at(intervals)
                fire(loop)
                self.assertEqual(frame, spinner.text)
                seconds, callback = loop.set_alarm_in.call_args.args
                self.assertAlmostEqual(delay * INTERVAL, seconds)
                self.assertEqual(spinner._tick, callback)
        self.assertEqual(5, loop.set_alarm_in.call_count)

    def test_step_while_running(self) -> None:
        """step() while running shifts the frame by one, and later ticks keep the shift."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        spinner.step()
        self.assertEqual("\\", spinner.text)
        self.at(1)
        fire(loop)
        self.assertEqual("|", spinner.text)

    def test_stop(self) -> None:
        """stop() removes the pending alarm and shows idle; a second stop() removes nothing; start() begins again."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        self.at(1)
        fire(loop)
        spinner.stop()
        loop.remove_alarm.assert_called_once_with("alarm 1")
        self.assertFalse(spinner.running)
        self.assertEqual(" ", spinner.text)
        spinner.stop()
        loop.remove_alarm.assert_called_once()
        self.at(3)
        spinner.start()
        self.assertEqual("-", spinner.text)
        self.at(4)
        fire(loop)
        self.assertEqual("\\", spinner.text)

    def test_interval_while_running(self) -> None:
        """A new interval replaces the alarm, keeps the frame showing, and the next tick shows the next frame."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        self.at(1)
        fire(loop)
        self.assertEqual("\\", spinner.text)
        # The alarm for frame 2 is overdue: the clock is already past it.
        self.at(3)
        spinner.interval = 2 * INTERVAL
        loop.remove_alarm.assert_called_once_with("alarm 1")
        loop.set_alarm_in.assert_called_with(2 * INTERVAL, spinner._tick)
        self.assertEqual("\\", spinner.text)
        self.at(5)
        fire(loop)
        self.assertEqual("|", spinner.text)

    def test_interval_while_stopped(self) -> None:
        """A new interval on a stopped spinner is only stored."""
        loop = mock_loop()
        spinner = urwid.Spinner(loop=loop)
        spinner.interval = INTERVAL
        self.assertEqual(INTERVAL, spinner.interval)
        loop.set_alarm_in.assert_not_called()

    def test_idle_while_running(self) -> None:
        """A new idle text on a running spinner shows from the next stop()."""
        spinner = urwid.Spinner(interval=INTERVAL, loop=mock_loop())
        spinner.start()
        spinner.idle = "done"
        self.assertEqual("-", spinner.text)
        spinner.stop()
        self.assertEqual("done", spinner.text)


class SpinnerFailureTest(ClockTestCase):
    """A call that fails leaves the spinner as it was, or stopped, never running without an alarm."""

    def assert_restartable(self, spinner: urwid.Spinner, loop: unittest.mock.Mock) -> None:
        """Check that *spinner* is stopped and idle, and that start() sets an alarm again."""
        self.assertFalse(spinner.running)
        self.assertEqual(" ", spinner.text)
        loop.set_alarm_in.side_effect = None
        loop.set_alarm_in.return_value = "again"
        spinner.start()
        self.assertTrue(spinner.running)
        loop.set_alarm_in.assert_called_with(spinner.interval, spinner._tick)

    def test_start_alarm_fails(self) -> None:
        """set_alarm_in() raising in start() leaves the spinner idle and stopped."""
        loop = mock_loop()
        loop.set_alarm_in.side_effect = OSError("no alarm")
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        with self.assertRaises(OSError):
            spinner.start()
        self.assert_restartable(spinner, loop)

    def test_tick_alarm_fails(self) -> None:
        """set_alarm_in() raising on the re-arm propagates from the tick and leaves the spinner stopped and idle."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        loop.set_alarm_in.side_effect = OSError("no alarm")
        self.at(1)
        with self.assertRaises(OSError):
            fire(loop, 0)
        self.assert_restartable(spinner, loop)

    def test_interval_alarm_fails(self) -> None:
        """set_alarm_in() raising in the interval setter removes the old alarm, stores the value, and stops."""
        loop = mock_loop()
        spinner = urwid.Spinner(interval=INTERVAL, loop=loop)
        spinner.start()
        loop.set_alarm_in.side_effect = OSError("no alarm")
        with self.assertRaises(OSError):
            spinner.interval = 2 * INTERVAL
        loop.remove_alarm.assert_called_once_with("alarm 0")
        self.assertEqual(2 * INTERVAL, spinner.interval)
        self.assert_restartable(spinner, loop)


class SpinnerRunningLoopTest(unittest.TestCase):
    """Alarms set on the running loop."""

    def run(self, result: unittest.TestResult | None = None) -> unittest.TestResult | None:
        """Run each test in an empty context, so a loop a failed test left running cannot reach the next one."""
        return contextvars.Context().run(super().run, result)

    def test_no_running_loop(self) -> None:
        """start() with no loop given and none running raises RuntimeError and leaves the spinner idle."""
        spinner = urwid.Spinner()
        with self.assertRaises(RuntimeError):
            spinner.start()
        self.assertFalse(spinner.running)
        self.assertEqual(" ", spinner.text)

    def test_ticks_on_running_loop(self) -> None:
        """A spinner started inside an alarm uses the running loop, re-arms from its tick, and stop() removes it."""
        loop = external_loop()
        spinner = urwid.Spinner(interval=0.01)
        seen: dict[str, typing.Any] = {}
        original_set_alarm_in = loop.set_alarm_in
        set_alarm_in = unittest.mock.patch.object(loop, "set_alarm_in").start()
        remove_alarm = unittest.mock.patch.object(loop, "remove_alarm", wraps=loop.remove_alarm).start()
        self.addCleanup(unittest.mock.patch.stopall)
        tick_handles: list[typing.Any] = []

        def finish(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            try:
                seen["before"] = (list(set_alarm_in.call_args_list), list(remove_alarm.call_args_list), spinner.running)
                spinner.stop()
                seen["after"] = (list(set_alarm_in.call_args_list), list(remove_alarm.call_args_list), spinner.running)
            finally:
                raise urwid.ExitMainLoop

        def count_ticks(seconds: float, callback: typing.Any, user_data: typing.Any = None) -> typing.Any:
            handle = original_set_alarm_in(seconds, callback, user_data)
            if getattr(callback, "__self__", None) is spinner:
                tick_handles.append(handle)
                if len(tick_handles) == 2:
                    original_set_alarm_in(0, finish)
            return handle

        def begin(_loop: urwid.MainLoop, _data: object) -> None:
            spinner.start()

        def timeout(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen["timeout"] = True
            raise urwid.ExitMainLoop

        set_alarm_in.side_effect = count_ticks
        loop.set_alarm_in(0, begin)
        loop.set_alarm_in(5, timeout)
        loop.run()

        self.assertNotIn("timeout", seen)
        self.assertIsNone(spinner.loop)
        calls, removed, running = seen["before"]
        self.assertEqual(2, sum(getattr(call.args[1], "__self__", None) is spinner for call in calls))
        self.assertEqual([], removed)
        self.assertTrue(running)
        calls, removed, running = seen["after"]
        self.assertEqual([unittest.mock.call(tick_handles[1])], removed)
        self.assertFalse(running)

    def test_given_loop_wins(self) -> None:
        """The loop given to the spinner gets the alarm even while another loop is running."""
        given = mock_loop()
        spinner = urwid.Spinner(loop=given)
        running = external_loop()

        def begin(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            try:
                spinner.start()
            finally:
                raise urwid.ExitMainLoop

        def timeout(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            raise urwid.ExitMainLoop

        running.set_alarm_in(0, begin)
        running.set_alarm_in(5, timeout)
        running.run()
        given.set_alarm_in.assert_called_once_with(spinner.interval, spinner._tick)
        self.assertIs(given, spinner.loop)
        spinner.stop()


class SpinnerLifetimeTest(unittest.TestCase):
    """References held through the loop's alarm."""

    def test_stopped_spinner_is_freed(self) -> None:
        """After stop() the loop holds no alarm, and the spinner is freed once the test drops it."""
        loop = external_loop()
        spinner = urwid.Spinner(loop=loop)
        spinner.start()
        self.assertEqual(1, len(loop.event_loop._alarms))
        spinner.stop()
        self.assertEqual([], loop.event_loop._alarms)
        ref = weakref.ref(spinner)
        del spinner
        self.assertEqual(0, collect_and_count_alive([ref]))

    def test_running_spinner_is_kept(self) -> None:
        """A running spinner is kept alive by its pending alarm until it is stopped."""
        loop = external_loop()
        spinner = urwid.Spinner(loop=loop)
        spinner.start()
        ref = weakref.ref(spinner)
        del spinner
        self.assertEqual(1, collect_and_count_alive([ref]))
        kept = ref()
        if kept is None:
            self.fail("the running spinner was freed")
        kept.stop()
