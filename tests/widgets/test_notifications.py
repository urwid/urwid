"""Tests for :class:`urwid.Notifications`."""

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
from urwid.testing import VirtualClockEventLoop, check_sizing, render_runs, render_text

if typing.TYPE_CHECKING:
    from collections.abc import Callable

INFO = urwid.Severity.INFO
WARNING = urwid.Severity.WARNING
ERROR = urwid.Severity.ERROR


def mock_loop() -> unittest.mock.Mock:
    """Return a mock ``MainLoop`` whose ``set_alarm_in`` returns the handles ``"alarm 0"``, ``"alarm 1"``, ..."""
    loop = unittest.mock.Mock(spec=urwid.MainLoop)
    loop.set_alarm_in.side_effect = (f"alarm {n}" for n in itertools.count())
    return loop


def fire(loop: unittest.mock.Mock, call: int = -1) -> None:
    """Call the alarm callback of the *call*-th ``set_alarm_in`` call of *loop*, as the loop does when it fires."""
    _seconds, callback = loop.set_alarm_in.call_args_list[call].args
    callback(loop, None)


def record(widget: urwid.Notifications) -> list[urwid.Notifications]:
    """Return the list the ``"change"`` signals of *widget* are appended to."""
    seen: list[urwid.Notifications] = []
    urwid.connect_signal(widget, "change", seen.append)
    return seen


def post_nested_once(widget: urwid.Notifications) -> None:
    """Disconnect this ``"change"`` handler from *widget*, then post ``"nested"`` on it."""
    urwid.disconnect_signal(widget, "change", post_nested_once)
    widget.notify("nested")


def texts(widget: urwid.Notifications) -> list[str]:
    """Return the text of the messages showing, the oldest first."""
    return [notification.widget.text for notification in widget.notifications]


class NotificationsConstructionTest(unittest.TestCase):
    """Building a ``Notifications`` and validating its arguments."""

    def test_defaults(self) -> None:
        """A new widget is empty, has a five-second timeout and no limit, and its repr names no argument."""
        widget = urwid.Notifications()
        self.assertEqual((), widget.notifications)
        self.assertEqual(5.0, widget.timeout)
        self.assertIsNone(widget.max_count)
        self.assertEqual({}, widget.severity_attr)
        self.assertIsNone(widget.default)
        self.assertIsNone(widget.default_attr)
        self.assertIsNone(widget.loop)
        self.assertEqual("<Notifications flow widget (0 messages)>", repr(widget))

    def test_repr(self) -> None:
        """The repr counts the messages and names the arguments that differ from their defaults."""
        widget = urwid.Notifications(timeout=None, max_count=1, default="ready")
        notification = widget.notify("saved", severity=WARNING)
        self.assertEqual(
            "<Notifications flow widget (1 message) default='ready' max_count=1 timeout=None>",
            repr(widget),
        )
        self.assertEqual("<Notification 'saved' severity=WARNING>", repr(notification))

    def test_invalid_arguments(self) -> None:
        """Invalid constructor arguments raise the documented exceptions."""
        for description, kwargs, error in (
            ("zero timeout", {"timeout": 0}, ValueError),
            ("negative timeout", {"timeout": -1.5}, ValueError),
            ("NaN timeout", {"timeout": math.nan}, ValueError),
            ("infinite timeout", {"timeout": math.inf}, ValueError),
            ("bool timeout", {"timeout": True}, TypeError),
            ("str timeout", {"timeout": "5"}, TypeError),
            ("zero max_count", {"max_count": 0}, ValueError),
            ("float max_count", {"max_count": 1.0}, TypeError),
            ("bool max_count", {"max_count": True}, TypeError),
            ("str max_count", {"max_count": "1"}, TypeError),
            ("int severity key", {"severity_attr": {1: "error"}}, TypeError),
            ("unhashable attr", {"default_attr": {"a": []}}, urwid.AttrMapError),
            ("bad default", {"default": 1}, urwid.TagMarkupException),
            ("bad align", {"align": "middle"}, urwid.TextError),
            ("bad wrap", {"wrap": "sideways"}, urwid.TextError),
        ):
            with self.subTest(description), self.assertRaises(error):
                urwid.Notifications(**kwargs)

    def test_invalid_notify_arguments(self) -> None:
        """Invalid notify() arguments raise the documented exceptions."""
        widget = urwid.Notifications(timeout=None)
        for description, args, kwargs, error in (
            ("int severity", ("x",), {"severity": 1}, TypeError),
            ("zero timeout", ("x",), {"timeout": 0}, ValueError),
            ("str timeout", ("x",), {"timeout": "5"}, TypeError),
            ("bad markup", (1,), {}, urwid.TagMarkupException),
        ):
            with self.subTest(description), self.assertRaises(error):
                widget.notify(*args, **kwargs)
        self.assertEqual((), widget.notifications)


class NotificationsRenderTest(unittest.TestCase):
    """Sizing and rendering."""

    def test_sizing_is_flow_whatever_shows(self) -> None:
        """The widget is flow only when empty, when showing the default text and when showing messages."""
        empty = urwid.Notifications(timeout=None)
        with_default = urwid.Notifications(timeout=None, default="ready")
        populated = urwid.Notifications(timeout=None)
        populated.notify("one")
        populated.notify("two")
        for description, widget in (("empty", empty), ("default", with_default), ("populated", populated)):
            with self.subTest(description):
                self.assertEqual(frozenset((urwid.FLOW,)), widget.sizing())
                check_sizing(widget)

    def test_empty_takes_no_rows(self) -> None:
        """Without messages and without a default text the widget renders zero rows."""
        widget = urwid.Notifications()
        self.assertEqual(0, widget.rows((10,)))
        self.assertEqual([], render_text(widget, (10,)))

    def test_oldest_first(self) -> None:
        """Messages are listed in the order they were posted, each wrapped to the width."""
        widget = urwid.Notifications(timeout=None)
        widget.notify("first")
        widget.notify("second message")
        self.assertEqual(["first", "second", "message"], render_text(widget, (8,), strip=True))

    def test_severity_attr(self) -> None:
        """A message takes its severity's attribute map, and a severity without an entry is left bare."""
        widget = urwid.Notifications(timeout=None, severity_attr={WARNING: "warn", ERROR: {None: "err"}})
        widget.notify("i")
        widget.notify("w", severity=WARNING)
        widget.notify("e", severity=ERROR)
        self.assertEqual([[(None, "i")], [("warn", "w")], [("err", "e")]], render_runs(widget, (1,)))

    def test_default_text(self) -> None:
        """The default text shows while no message is showing, with its attribute map."""
        widget = urwid.Notifications(timeout=None, default="ready", default_attr="dim")
        self.assertEqual([[("dim", "ready")]], render_runs(widget, (5,)))
        first = widget.notify("saved")
        self.assertEqual([[(None, "saved")]], render_runs(widget, (5,)))
        self.assertTrue(widget.dismiss(first))
        self.assertEqual([[("dim", "ready")]], render_runs(widget, (5,)))
        widget.notify("a")
        widget.notify("b")
        widget.clear()
        self.assertEqual(["ready"], render_text(widget, (5,)))

    def test_align_and_wrap(self) -> None:
        """``align`` and ``wrap`` apply to every message and to the default text."""
        widget = urwid.Notifications(timeout=None, align="right", wrap="clip", default="ready")
        self.assertEqual(["   ready"], render_text(widget, (8,)))
        widget.notify("a long message")
        self.assertEqual([" message"], render_text(widget, (8,)))
        widget.clear()
        widget.notify("ok")
        self.assertEqual(["      ok"], render_text(widget, (8,)))

    def test_status_line(self) -> None:
        """With ``max_count=1`` a new message replaces the one showing."""
        widget = urwid.Notifications(timeout=None, max_count=1)
        widget.notify("one")
        widget.notify("two")
        self.assertEqual(["two"], render_text(widget, (3,)))

    def test_footer_redraws(self) -> None:
        """A ``Frame`` footer shows each change in the next render."""
        widget = urwid.Notifications(timeout=None)
        frame = urwid.Frame(urwid.SolidFill("."), footer=widget)
        self.assertEqual(["...", "..."], render_text(frame, (3, 2)))
        notification = widget.notify("hi")
        self.assertEqual(["...", "hi "], render_text(frame, (3, 2)))
        widget.dismiss(notification)
        self.assertEqual(["...", "..."], render_text(frame, (3, 2)))


class NotificationsAlarmTest(unittest.TestCase):
    """Alarms set on the loop given to the widget."""

    def test_alarm_set_and_fired(self) -> None:
        """notify() sets an alarm with the timeout, and the alarm firing dismisses the message."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        notification = widget.notify("saved")
        widget.notify("other", timeout=2)
        self.assertEqual([5.0, 2], [c.args[0] for c in loop.set_alarm_in.call_args_list])
        self.assertEqual((notification,), loop.set_alarm_in.call_args_list[0].args[1].args)
        self.assertEqual((INFO, 5.0), (notification.severity, notification.timeout))
        fire(loop, 0)
        self.assertEqual(["other"], texts(widget))
        self.assertEqual({id(widget.notifications[0])}, {id(n) for n in widget._alarms})
        loop.remove_alarm.assert_not_called()
        self.assertFalse(widget.dismiss(notification))
        loop.remove_alarm.assert_not_called()

    def test_dismiss_removes_alarm(self) -> None:
        """dismiss() removes the pending alarm once; a second dismiss() returns False and removes nothing."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        notification = widget.notify("saved")
        self.assertTrue(widget.dismiss(notification))
        loop.remove_alarm.assert_called_once_with("alarm 0")
        self.assertFalse(widget.dismiss(notification))
        loop.remove_alarm.assert_called_once_with("alarm 0")
        self.assertEqual({}, widget._alarms)

    def test_persistent_message_sets_no_alarm(self) -> None:
        """``timeout=None`` on notify() or on the widget sets no alarm."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        widget.notify("sticky", timeout=None)
        widget.timeout = None
        widget.notify("also sticky")
        loop.set_alarm_in.assert_not_called()
        widget.clear()
        loop.remove_alarm.assert_not_called()

    def test_eviction_removes_alarm(self) -> None:
        """A message over ``max_count`` dismisses the oldest and removes its alarm."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop, max_count=4)
        for text in ("a", "b", "c", "d"):
            widget.notify(text)
        self.assertEqual(["a", "b", "c", "d"], texts(widget))
        loop.remove_alarm.assert_not_called()
        widget.notify("e")
        self.assertEqual(["b", "c", "d", "e"], texts(widget))
        loop.remove_alarm.assert_called_once_with("alarm 0")

    def test_clear_removes_every_alarm(self) -> None:
        """clear() removes every pending alarm."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        widget.notify("a")
        widget.notify("b", timeout=None)
        widget.notify("c")
        widget.clear()
        self.assertEqual(
            [unittest.mock.call("alarm 0"), unittest.mock.call("alarm 1")],
            loop.remove_alarm.call_args_list,
        )
        self.assertEqual({}, widget._alarms)


class NotificationsFailureTest(unittest.TestCase):
    """A notify() that fails leaves the widget as it was."""

    def run(self, result: unittest.TestResult | None = None) -> unittest.TestResult | None:
        """Run each test in an empty context, so no loop is running."""
        return contextvars.Context().run(super().run, result)

    def test_failed_notify_changes_nothing(self) -> None:
        """Each failing notify() raises, and the message showing, its alarm and the signal count are kept."""
        failing_loop = mock_loop()
        failing_loop.set_alarm_in.side_effect = OSError
        for description, loop, kwargs, error in (
            ("no running loop", None, {}, RuntimeError),
            ("set_alarm_in raises", failing_loop, {}, OSError),
            ("bad severity", None, {"severity": "error"}, TypeError),
            ("bad timeout", None, {"timeout": -1}, ValueError),
            ("bad markup", None, {"markup": 1}, urwid.TagMarkupException),
        ):
            with self.subTest(description):
                widget = urwid.Notifications(max_count=1, loop=loop)
                first = widget.notify("first", timeout=None)
                changes = record(widget)
                with self.assertRaises(error):
                    widget.notify(**{"markup": "second", **kwargs})
                self.assertEqual((first,), widget.notifications)
                self.assertEqual({}, widget._alarms)
                self.assertEqual([], changes)
                self.assertEqual(["first"], render_text(widget, (5,)))


class NotificationsSignalTest(unittest.TestCase):
    """The ``"change"`` signal."""

    def test_counts(self) -> None:
        """Each operation that changes the messages sends one signal, and one that changes nothing sends none."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop, max_count=2)
        changes = record(widget)
        steps: list[tuple[str, Callable[[], object], int]] = [
            ("notify", lambda: widget.notify("a"), 1),
            ("notify", lambda: widget.notify("b"), 1),
            ("notify with eviction", lambda: widget.notify("c"), 1),
            ("dismiss stale", lambda: widget.dismiss(urwid.Notification(urwid.Text("x"), INFO, None)), 0),
            ("expiry", lambda: fire(loop), 1),
            ("dismiss showing", lambda: widget.dismiss(widget.notifications[0]), 1),
            ("clear empty", widget.clear, 0),
            ("notify", lambda: widget.notify("d"), 1),
            ("clear", widget.clear, 1),
        ]
        for description, step, expected in steps:
            with self.subTest(description):
                before = len(changes)
                step()
                self.assertEqual(expected, len(changes) - before)
        self.assertEqual({id(widget)}, {id(sent) for sent in changes})

    def test_handler_clearing(self) -> None:
        """A handler that clears on every signal leaves the widget empty with no pending alarm."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        urwid.connect_signal(widget, "change", lambda w: w.clear())
        widget.notify("a")
        self.assertEqual((), widget.notifications)
        self.assertEqual({}, widget._alarms)
        loop.remove_alarm.assert_called_once_with("alarm 0")

    def test_handler_posting(self) -> None:
        """A handler that posts once, with and without ``max_count=1``, sees a consistent widget."""
        for max_count, expected, removed in ((None, ["outer", "nested"], []), (1, ["nested"], ["alarm 0"])):
            with self.subTest(max_count=max_count):
                loop = mock_loop()
                widget = urwid.Notifications(loop=loop, max_count=max_count)
                changes = record(widget)
                urwid.connect_signal(widget, "change", post_nested_once)
                widget.notify("outer")
                self.assertEqual(expected, texts(widget))
                self.assertEqual(set(widget.notifications), set(widget._alarms))
                self.assertEqual(removed, [c.args[0] for c in loop.remove_alarm.call_args_list])
                self.assertEqual(2, len(changes))

    def test_handler_raising(self) -> None:
        """An exception from a handler reaches the caller after the message is showing with its alarm."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)

        def fail(_w: urwid.Notifications) -> None:
            raise ZeroDivisionError

        urwid.connect_signal(widget, "change", fail)
        with self.assertRaises(ZeroDivisionError):
            widget.notify("a")
        self.assertEqual(["a"], texts(widget))
        self.assertEqual(set(widget.notifications), set(widget._alarms))


class NotificationsPropertyTest(unittest.TestCase):
    """The writable properties."""

    def test_max_count(self) -> None:
        """Lowering ``max_count`` evicts the oldest at once with one signal, and nothing when none is over it."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        for text in ("a", "b", "c"):
            widget.notify(text)
        changes = record(widget)
        widget.max_count = 3
        self.assertEqual([], changes)
        widget.max_count = 1
        self.assertEqual(["c"], texts(widget))
        self.assertEqual(["alarm 0", "alarm 1"], [c.args[0] for c in loop.remove_alarm.call_args_list])
        self.assertEqual(1, len(changes))
        widget.max_count = None
        self.assertEqual(1, len(changes))

    def test_timeout(self) -> None:
        """Setting ``timeout`` applies to the next message and leaves the pending alarms alone."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        widget.notify("a")
        widget.timeout = 1.5
        self.assertEqual(1, loop.set_alarm_in.call_count)
        loop.remove_alarm.assert_not_called()
        widget.notify("b")
        self.assertEqual(1.5, loop.set_alarm_in.call_args.args[0])

    def test_severity_attr(self) -> None:
        """Setting ``severity_attr`` re-colours the messages showing; the returned dict is a copy."""
        widget = urwid.Notifications(timeout=None, severity_attr={ERROR: "err"})
        widget.notify("e", severity=ERROR)
        changes = record(widget)
        widget.severity_attr[ERROR][None] = "changed"
        self.assertEqual([[("err", "e")]], render_runs(widget, (1,)))
        widget.severity_attr = {ERROR: "bad"}
        self.assertEqual([[("bad", "e")]], render_runs(widget, (1,)))
        self.assertEqual({ERROR: {None: "bad"}}, widget.severity_attr)
        widget.severity_attr = None
        self.assertEqual([[(None, "e")]], render_runs(widget, (1,)))
        self.assertEqual([], changes)

    def test_default(self) -> None:
        """Setting the default text or its map shows at once while empty, and only once empty otherwise."""
        loop = mock_loop()
        widget = urwid.Notifications(loop=loop)
        changes = record(widget)
        widget.default = "ready"
        widget.default_attr = "dim"
        self.assertEqual("ready", widget.default)
        self.assertEqual({None: "dim"}, widget.default_attr)
        self.assertEqual([[("dim", "ready")]], render_runs(widget, (5,)))
        notification = widget.notify("saved")
        widget.default = "idle"
        widget.default_attr = None
        self.assertEqual(["saved"], render_text(widget, (5,)))
        self.assertEqual((notification,), widget.notifications)
        loop.remove_alarm.assert_not_called()
        widget.dismiss(notification)
        self.assertEqual([[(None, "idle ")]], render_runs(widget, (5,)))
        widget.default = None
        self.assertEqual([], render_text(widget, (5,)))
        self.assertEqual(2, len(changes))

    def test_invalid_assignment_keeps_value(self) -> None:
        """An invalid assignment raises, and the property and the next render are unchanged."""
        widget = urwid.Notifications(timeout=2, max_count=2, severity_attr={ERROR: "err"}, default="ready")
        widget.default_attr = "dim"
        before = render_runs(widget, (5,))
        for name, value, error in (
            ("timeout", 0, ValueError),
            ("max_count", 0, ValueError),
            ("severity_attr", {"error": "err"}, TypeError),
            ("default", 1, urwid.TagMarkupException),
            ("default_attr", {"a": []}, urwid.AttrMapError),
        ):
            with self.subTest(name):
                old = getattr(widget, name)
                with self.assertRaises(error):
                    setattr(widget, name, value)
                self.assertEqual(old, getattr(widget, name))
                self.assertEqual(before, render_runs(widget, (5,)))


class NotificationsRunningLoopTest(unittest.TestCase):
    """Alarms set on the running loop."""

    def run(self, result: unittest.TestResult | None = None) -> unittest.TestResult | None:
        """Run each test in an empty context, so a loop a failed test left running cannot reach the next one."""
        return contextvars.Context().run(super().run, result)

    def test_no_running_loop(self) -> None:
        """A timed message with no loop given and none running raises RuntimeError; a persistent one does not."""
        widget = urwid.Notifications()
        with self.assertRaises(RuntimeError):
            widget.notify("saved")
        widget.notify("sticky", timeout=None)
        self.assertEqual(["sticky"], texts(widget))

    def test_given_loop_wins(self) -> None:
        """The loop given to the widget gets the alarm even while another loop is running."""
        given = mock_loop()
        widget = urwid.Notifications(loop=given)
        running = external_loop()
        seen: list[urwid.MainLoop] = []

        def post(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            widget.notify("saved")
            seen.append(urwid.get_running_loop())
            raise urwid.ExitMainLoop

        def stop(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            raise urwid.ExitMainLoop

        running.set_alarm_in(0, post)
        # the guard: it ends the run when notify() raises inside post
        running.set_alarm_in(1, stop)
        running.run()
        self.assertEqual([running], seen)
        given.set_alarm_in.assert_called_once()
        self.assertIs(given, widget.loop)

    def test_expires_on_running_loop(self) -> None:
        """A message posted inside an alarm uses the running loop, and expires through its real alarm."""
        widget = urwid.Notifications(timeout=0.01)
        loop = external_loop(event_loop=VirtualClockEventLoop())
        seen: list[list[str]] = []

        def post(_loop: urwid.MainLoop, _data: object) -> None:
            widget.notify("saved")
            seen.append(texts(widget))

        def check(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            seen.append(texts(widget))
            raise urwid.ExitMainLoop

        loop.set_alarm_in(0, post)
        # also the guard: it ends the run whether or not the message expired
        loop.set_alarm_in(0.2, check)
        loop.run()
        self.assertEqual([["saved"], []], seen)
        self.assertIsNone(widget.loop)


class NotificationsLifetimeTest(unittest.TestCase):
    """References held through the loop's alarms."""

    def test_dismissed_message_is_freed(self) -> None:
        """A dismissed timed message, its widget and the ``Notifications`` are freed, and no alarm is left."""
        loop = external_loop()
        widget = urwid.Notifications(loop=loop)
        notification = widget.notify("saved")
        refs: list[weakref.ReferenceType[typing.Any]] = [weakref.ref(notification), weakref.ref(notification.widget)]
        self.assertTrue(widget.dismiss(notification))
        del notification
        self.assertEqual(0, collect_and_count_alive(refs))
        self.assertEqual([], loop.event_loop._alarms)
        widget_ref = weakref.ref(widget)
        del widget
        self.assertEqual(0, collect_and_count_alive([widget_ref]))

    def test_expired_message_is_freed(self) -> None:
        """A message that expired through the loop's alarm is freed, and no alarm is left."""
        loop = external_loop(event_loop=VirtualClockEventLoop())
        widget = urwid.Notifications(loop=loop, timeout=0.01)
        refs: list[weakref.ReferenceType[typing.Any]] = []

        def post(_loop: urwid.MainLoop, _data: object) -> None:
            notification = widget.notify("saved")
            refs.extend((weakref.ref(notification), weakref.ref(notification.widget)))

        def stop(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            raise urwid.ExitMainLoop

        loop.set_alarm_in(0, post)
        loop.set_alarm_in(0.2, stop)
        loop.run()
        self.assertEqual((), widget.notifications)
        self.assertEqual(0, collect_and_count_alive(refs))
        self.assertEqual([], loop.event_loop._alarms)
