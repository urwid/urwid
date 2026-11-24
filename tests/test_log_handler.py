"""Tests for :mod:`urwid.log_handler`."""

from __future__ import annotations

import contextvars
import logging
import sys
import threading
import typing
import unittest
import unittest.mock
import weakref

import urwid
from urwid import log_handler
from urwid.testing import ScriptedScreen, VirtualClockEventLoop

if typing.TYPE_CHECKING:
    from collections.abc import Callable

IS_CPYTHON = sys.implementation.name == "cpython"
# Seconds a test waits for a thread it started; the guard against a hang.
JOIN_TIMEOUT = 5.0


class UnwatchableEventLoop(VirtualClockEventLoop):
    """Event loop that cannot watch files, as asyncio's ``ProactorEventLoop``."""

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> typing.NoReturn:
        raise NotImplementedError


class CountingHandler(logging.Handler):
    """Handler that keeps the records it gets."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _HandlerTests:
    """Behaviour shared by both handlers; a subclass builds the handler and reads what it shows."""

    # Provided by unittest.TestCase in the subclasses.
    assertEqual: Callable[..., None]
    assertIs: Callable[..., None]
    assertTrue: Callable[..., None]
    assertFalse: Callable[..., None]
    assertRaises: Callable[..., typing.Any]
    assertRaisesRegex: Callable[..., typing.Any]
    assertLogs: Callable[..., typing.Any]
    assertNoLogs: Callable[..., typing.Any]
    assertLessEqual: Callable[..., None]
    subTest: Callable[..., typing.Any]
    addCleanup: Callable[..., None]
    id: Callable[[], str]

    def make_handler(self, loop: urwid.MainLoop, **kwargs: typing.Any) -> log_handler._LoopHandler:
        """Return a new handler on *loop*, showing into a new widget."""
        raise NotImplementedError

    def shown(self, handler: log_handler._LoopHandler) -> list[str]:
        """Return the texts the widget of *handler* shows, oldest first."""
        raise NotImplementedError

    def on_show(self, handler: log_handler._LoopHandler, callback: Callable[[], None]) -> None:
        """Call *callback* from the widget's own signal each time *handler* shows a record."""
        raise NotImplementedError

    def setUp(self) -> None:
        self.event_loop = VirtualClockEventLoop()
        self.loop = self.new_loop(self.event_loop)

    @staticmethod
    def new_loop(event_loop: urwid.EventLoop) -> urwid.MainLoop:
        """Return a loop over an unscripted screen on *event_loop*."""
        return urwid.MainLoop(urwid.SolidFill(), screen=ScriptedScreen(inputs=None), event_loop=event_loop)

    def start(self, loop: urwid.MainLoop | None = None) -> None:
        """Start *loop*, the test's loop by default, and stop it at the end of the test unless it was stopped."""
        loop = loop if loop is not None else self.loop
        loop.start()
        self.addCleanup(lambda: loop.stop() if urwid.get_running_loop_or_none() is loop else None)

    def handler(self, **kwargs: typing.Any) -> tuple[log_handler._LoopHandler, logging.Logger]:
        """Return a handler on the test's loop and a logger of this test that only it handles."""
        handler = self.make_handler(self.loop, **kwargs)
        logger = logging.getLogger(f"tests.log_handler.{self.id()}")
        logger.propagate = False
        logger.setLevel(1)
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(handler.close)
        return handler, logger

    @staticmethod
    def pending_calls(loop: urwid.MainLoop) -> int:
        """Return the number of call_from_thread() calls queued on *loop*."""
        state = loop._thread_calls
        assert state is not None
        return len(state.calls)

    # Hand-over and lifecycle

    def test_record_on_loop_thread_waits_for_the_loop(self) -> None:
        handler, logger = self.handler()
        self.start()
        logger.info("one")
        self.assertEqual([], self.shown(handler))
        self.event_loop.advance(0)
        self.assertEqual(["one"], self.shown(handler))

    def test_record_from_worker_thread_arrives_in_order(self) -> None:
        handler, logger = self.handler()
        self.start()
        logger.info("loop 1")
        worker = threading.Thread(target=logger.info, args=("worker",))
        worker.start()
        worker.join(JOIN_TIMEOUT)
        self.assertFalse(worker.is_alive())
        logger.info("loop 2")
        self.event_loop.advance(0)
        self.assertEqual(["loop 1", "worker", "loop 2"], self.shown(handler))

    def test_copied_context_still_hands_over(self) -> None:
        """A worker that sees the loop as running through a copied context changes nothing itself."""
        handler, logger = self.handler()
        threads: list[int] = []
        self.on_show(handler, lambda: threads.append(threading.get_ident()))
        self.start()
        context = contextvars.copy_context()

        def work() -> None:
            assert urwid.get_running_loop_or_none() is self.loop
            logger.info("worker")
            handler.resume()

        worker = threading.Thread(target=context.run, args=(work,))
        worker.start()
        worker.join(JOIN_TIMEOUT)
        self.assertFalse(worker.is_alive())
        self.assertEqual([], self.shown(handler))
        self.event_loop.advance(0)
        self.assertEqual(["worker"], self.shown(handler))
        self.assertEqual([threading.get_ident()], threads)

    def test_records_before_start_wait_for_resume(self) -> None:
        handler, logger = self.handler()
        logger.info("early 1")
        logger.info("early 2")
        with self.assertRaisesRegex(RuntimeError, "not running"):
            handler.resume()
        self.start()
        self.event_loop.advance(0)
        self.assertEqual([], self.shown(handler))
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["early 1", "early 2"], self.shown(handler))

    def test_restart_needs_resume(self) -> None:
        """A stop() that drops the queued call leaves the records for the next run's resume()."""
        handler, logger = self.handler()
        self.start()
        logger.info("first")
        self.loop.stop()
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["first"], self.shown(handler))
        logger.info("second")
        self.event_loop.advance(0)
        self.assertEqual(["first", "second"], self.shown(handler))

    def test_one_call_per_batch(self) -> None:
        handler, logger = self.handler()
        self.start()
        for number in range(5):
            logger.info("record %d", number)
        self.assertEqual(1, self.pending_calls(self.loop))
        handler.resume()
        logger.info("record 5")
        handler.resume()
        self.assertLessEqual(self.pending_calls(self.loop), 3)
        self.event_loop.advance(0)
        self.assertEqual([f"record {number}" for number in range(6)], self.shown(handler))

    def test_burst_keeps_the_newest(self) -> None:
        handler, logger = self.handler(max_pending=3)
        for number in range(5):
            logger.info("record %d", number)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["record 2", "record 3", "record 4"], self.shown(handler))

    def test_invalid_max_pending(self) -> None:
        with self.assertRaises(ValueError):
            self.make_handler(self.loop, max_pending=0)

    def test_invalid_level(self) -> None:
        for description, level, error in (("unknown name", "LOUD", ValueError), ("float", 1.5, TypeError)):
            with self.subTest(description), self.assertRaises(error):
                self.make_handler(self.loop, level=level)

    def test_drain_is_capped(self) -> None:
        """One drain shows the cap and queues one more call; records logged during delivery come after."""
        cap = log_handler._ENTRIES_PER_DRAIN
        handler, logger = self.handler()
        logged = False

        def log_once() -> None:
            nonlocal logged
            if not logged:
                logged = True
                logger.info("late")

        self.on_show(handler, log_once)
        for number in range(cap + 8):
            logger.info("record %d", number)
        self.start()
        handler._drain()
        self.assertEqual(cap, len(self.shown(handler)))
        self.assertEqual(1, self.pending_calls(self.loop))
        self.event_loop.advance(0)
        self.assertEqual([*(f"record {number}" for number in range(cap + 8)), "late"], self.shown(handler))

    def test_stop_during_delivery_keeps_the_rest(self) -> None:
        handler, logger = self.handler()
        stopped = False

        def stop_once() -> None:
            nonlocal stopped
            if not stopped:
                stopped = True
                self.loop.stop()

        self.on_show(handler, stop_once)
        for name in ("a", "b", "c"):
            logger.info(name)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["a"], self.shown(handler))
        self.assertEqual(2, len(handler._pending))
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["a", "b", "c"], self.shown(handler))

    def test_event_loop_that_cannot_watch_files(self) -> None:
        event_loop = UnwatchableEventLoop()
        self.loop = self.new_loop(event_loop)
        handler, logger = self.handler()
        self.start()
        logger.info("held")
        with self.assertRaisesRegex(RuntimeError, "cannot watch files"):
            handler.resume()
        event_loop.advance(0)
        self.assertEqual([], self.shown(handler))
        self.assertEqual(1, len(handler._pending))

    def test_nested_drain_shows_nothing(self) -> None:
        """A drain run from a widget callback during a drain leaves the rest to the outer one."""
        handler, logger = self.handler()
        seen_by_nested: list[list[str]] = []

        def nested_once() -> None:
            if not seen_by_nested:
                seen_by_nested.append([])
                logger.info("new")
                handler._drain()
                seen_by_nested[0] = self.shown(handler)

        self.on_show(handler, nested_once)
        for name in ("a", "b", "c"):
            logger.info(name)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual([["a"]], seen_by_nested)
        self.assertEqual(["a", "b", "c", "new"], self.shown(handler))

    def test_flush_shows_the_queue_at_once(self) -> None:
        """flush() on the loop thread shows every queued record, past the cap of one hand-over."""
        cap = log_handler._ENTRIES_PER_DRAIN
        handler, logger = self.handler()
        self.start()
        for number in range(cap + 8):
            logger.info("record %d", number)
        handler.flush()
        self.assertEqual([f"record {number}" for number in range(cap + 8)], self.shown(handler))
        self.event_loop.advance(0)
        self.assertEqual(cap + 8, len(self.shown(handler)))

    def test_flush_leaves_records_logged_during_it(self) -> None:
        """A record the widget logs while flush() shows the queue waits for the next hand-over."""
        handler, logger = self.handler()
        logged = False

        def log_once() -> None:
            nonlocal logged
            if not logged:
                logged = True
                logger.info("late")

        self.on_show(handler, log_once)
        self.start()
        logger.info("a")
        logger.info("b")
        handler.flush()
        self.assertEqual(["a", "b"], self.shown(handler))
        self.event_loop.advance(0)
        self.assertEqual(["a", "b", "late"], self.shown(handler))

    def test_flush_off_the_loop_thread_does_nothing(self) -> None:
        """flush() before the loop starts, or on another thread, keeps the records queued."""
        handler, logger = self.handler()
        logger.info("held")
        handler.flush()
        self.assertEqual([], self.shown(handler))
        self.start()
        worker = threading.Thread(target=handler.flush)
        worker.start()
        worker.join(JOIN_TIMEOUT)
        self.assertFalse(worker.is_alive())
        self.assertEqual([], self.shown(handler))
        handler.flush()
        self.assertEqual(["held"], self.shown(handler))

    def test_flush_off_the_loop_thread_leaves_hand_overs_alone(self) -> None:
        """A flush() on another thread, overlapping a hand-over and a new record, leaves them to the loop."""
        handler, logger = self.handler()
        self.start()
        logger.info("a")
        in_flush = threading.Event()
        release = threading.Event()
        worker: threading.Thread | None = None
        find_loop = urwid.get_running_loop_or_none

        def pausing_find_loop() -> urwid.MainLoop | None:
            if threading.current_thread() is worker and not in_flush.is_set():
                in_flush.set()
                release.wait(JOIN_TIMEOUT)
            return find_loop()

        with unittest.mock.patch.object(log_handler, "get_running_loop_or_none", pausing_find_loop):
            worker = threading.Thread(target=handler.flush)
            worker.start()
            try:
                self.assertTrue(in_flush.wait(JOIN_TIMEOUT))
                self.event_loop.advance(0)
                logger.info("b")
            finally:
                release.set()
                worker.join(JOIN_TIMEOUT)
        self.assertFalse(worker.is_alive())
        self.event_loop.advance(0)
        self.assertEqual(["a", "b"], self.shown(handler))

    def test_nested_flush_shows_nothing(self) -> None:
        """flush() from a widget callback during a hand-over leaves the rest to that hand-over."""
        handler, logger = self.handler()
        seen_by_nested: list[list[str]] = []

        def nested_once() -> None:
            if not seen_by_nested:
                handler.flush()
                seen_by_nested.append(self.shown(handler))

        self.on_show(handler, nested_once)
        for name in ("a", "b", "c"):
            logger.info(name)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual([["a"]], seen_by_nested)
        self.assertEqual(["a", "b", "c"], self.shown(handler))

    @unittest.skipUnless(IS_CPYTHON, "relies on reference counting to free the argument at once")
    def test_record_arguments_are_not_kept(self) -> None:
        class Argument:
            def __str__(self) -> str:
                return "argument"

        handler, logger = self.handler()
        argument = Argument()
        reference = weakref.ref(argument)
        mutable = ["before"]
        logger.info("%s %s", argument, mutable)
        del argument
        mutable[0] = "after"
        self.assertIsNone(reference())
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["argument ['before']"], self.shown(handler))

    # Shutdown

    def test_logging_shutdown_on_worker_thread(self) -> None:
        handler, logger = self.handler()
        logger.info("pending")
        worker = threading.Thread(target=logging.shutdown, args=([weakref.ref(handler)],))
        worker.start()
        worker.join(JOIN_TIMEOUT)
        self.assertFalse(worker.is_alive())
        self.assertTrue(handler._shut)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual([], self.shown(handler))

    def test_close_before_scheduled_drain(self) -> None:
        handler, logger = self.handler()
        self.start()
        logger.info("dropped")
        handler.close()
        with self.assertNoLogs("urwid.log_handler"):
            self.event_loop.advance(0)
        self.assertEqual([], self.shown(handler))
        logger.info("ignored")
        handler.resume()
        self.loop.stop()
        handler.resume()
        self.assertEqual([], self.shown(handler))
        self.assertEqual(0, len(handler._pending))

    def test_close_during_drain(self) -> None:
        handler, logger = self.handler()
        shows = 0

        def close_on_second() -> None:
            nonlocal shows
            shows += 1
            if shows == 2:
                handler.close()

        self.on_show(handler, close_on_second)
        for name in ("a", "b", "c", "d"):
            logger.info(name)
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["a", "b"], self.shown(handler))
        self.assertEqual(0, len(handler._pending))

    def test_close_releases_handler_lock_before_base_close(self) -> None:
        handler, _logger = self.handler()
        acquired: list[bool] = []
        base_close = logging.Handler.close

        def try_lock() -> None:
            if got := handler.lock.acquire(timeout=1):
                handler.lock.release()
            acquired.append(got)

        def checking_close(self_: logging.Handler) -> None:
            other = threading.Thread(target=try_lock)
            other.start()
            other.join(JOIN_TIMEOUT)
            base_close(self_)

        with unittest.mock.patch.object(logging.Handler, "close", checking_close):
            handler.close()
        self.assertEqual([True], acquired)

    # Failures

    def test_formatter_failure_goes_to_handle_error(self) -> None:
        class FailingFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                raise ValueError("cannot format")

        handler, logger = self.handler()
        handler.setFormatter(FailingFormatter())
        self.start()
        with unittest.mock.patch.object(handler, "handleError") as handle_error:
            logger.info("record")
        handle_error.assert_called_once()
        self.event_loop.advance(0)
        self.assertEqual([], self.shown(handler))

    def test_delivery_failure_is_logged_and_the_next_entry_shown(self) -> None:
        handler, logger = self.handler()
        failed = False

        def fail_once() -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise ValueError("widget callback failed")

        self.on_show(handler, fail_once)
        self.start()
        logger.info("a")
        logger.info("b")
        with self.assertLogs("urwid.log_handler", logging.ERROR) as logs:
            self.event_loop.advance(0)
        self.assertEqual(1, len(logs.records))
        self.assertEqual(["a", "b"], self.shown(handler))

    def _exit_during_delivery(self) -> log_handler._LoopHandler:
        """Return a handler whose first delivery raises ExitMainLoop after more records were logged than fit."""
        handler, logger = self.handler(max_pending=4)
        raised = False

        def exit_once() -> None:
            nonlocal raised
            if not raised:
                raised = True
                for number in range(5):
                    logger.info("late %d", number)
                raise urwid.ExitMainLoop

        self.on_show(handler, exit_once)
        for name in ("a", "b", "c"):
            logger.info(name)
        self.start()
        handler.resume()
        with self.assertRaises(urwid.ExitMainLoop):
            self.event_loop.advance(0)
        self.assertEqual(["a"], self.shown(handler))
        self.assertEqual(["late 1", "late 2", "late 3", "late 4"], [text for text, _ in handler._pending])
        return handler

    def test_exit_during_delivery_loop_goes_on(self) -> None:
        handler = self._exit_during_delivery()
        self.event_loop.advance(0)
        self.assertEqual(["a", "late 1", "late 2", "late 3", "late 4"], self.shown(handler))

    def test_exit_during_delivery_run_ends(self) -> None:
        handler = self._exit_during_delivery()
        self.loop.stop()
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        self.assertEqual(["a", "late 1", "late 2", "late 3", "late 4"], self.shown(handler))

    def test_failing_target_on_root_logger_settles(self) -> None:
        """A failure report of the handler does not come back to it, also without the urwid filter."""
        handler = self.make_handler(self.loop, level=logging.INFO)
        handler.removeFilter(handler.urwid_filter)
        self.addCleanup(handler.close)
        counter = CountingHandler()
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        root.setLevel(logging.DEBUG)
        for added in (handler, counter):
            root.addHandler(added)
            self.addCleanup(root.removeHandler, added)

        def fail() -> None:
            raise ValueError("widget callback failed")

        self.on_show(handler, fail)
        self.start()
        logger = logging.getLogger(f"tests.log_handler.{self.id()}")
        for name in ("a", "b", "c"):
            logger.info(name)
        self.event_loop.advance(0)
        failures = [record for record in counter.records if record.name == "urwid.log_handler"]
        self.assertEqual(3, len(failures))
        self.assertEqual(0, len(handler._pending))

    # Feedback through the urwid loggers

    def test_urwid_records_are_filtered(self) -> None:
        handler, logger = self.handler()
        self.start()
        urwid_logger = logging.getLogger("urwid")
        urwid_logger.addHandler(handler)
        self.addCleanup(urwid_logger.removeHandler, handler)
        child = logging.getLogger("urwid.x")
        self.addCleanup(urwid_logger.setLevel, urwid_logger.level)
        self.addCleanup(child.setLevel, child.level)
        urwid_logger.setLevel(logging.DEBUG)
        child.setLevel(logging.DEBUG)
        for record_logger in (urwid_logger, child):
            record_logger.info("info %s", record_logger.name)
            record_logger.debug("debug %s", record_logger.name)
        logger.info("own")
        self.event_loop.advance(0)
        self.assertEqual(["own"], self.shown(handler))

        handler.setLevel(logging.INFO)
        handler.removeFilter(handler.urwid_filter)
        for record_logger in (urwid_logger, child):
            record_logger.info("info %s", record_logger.name)
            record_logger.debug("debug %s", record_logger.name)
        self.event_loop.advance(0)
        self.assertEqual(["own", "info urwid", "info urwid.x"], self.shown(handler))


class ListWalkerHandlerTest(_HandlerTests, unittest.TestCase):
    def make_handler(self, loop: urwid.MainLoop, **kwargs: typing.Any) -> log_handler.ListWalkerHandler:
        walker = urwid.SimpleFocusDequeWalker([])
        return log_handler.ListWalkerHandler(walker, loop=loop, **kwargs)

    @staticmethod
    def walker(handler: log_handler._LoopHandler) -> urwid.SimpleFocusDequeWalker:
        """Return the walker *handler* appends to."""
        assert isinstance(handler, log_handler.ListWalkerHandler)
        assert isinstance(handler.walker, urwid.SimpleFocusDequeWalker)
        return handler.walker

    def shown(self, handler: log_handler._LoopHandler) -> list[str]:
        return [typing.cast("urwid.Text", row).text for row in self.walker(handler)]

    def on_show(self, handler: log_handler._LoopHandler, callback: Callable[[], None]) -> None:
        urwid.connect_signal(self.walker(handler), "modified", callback)

    def test_level_to_severity(self) -> None:
        names = {severity: severity.name for severity in urwid.Severity}
        handler, logger = self.handler(severity_attr=names)
        cases = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
            (logging.INFO + 5, "INFO"),
            (logging.DEBUG - 5, "DEBUG"),
        ]
        for level, _expected in cases:
            logger.log(level, "x")
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        walker = self.walker(handler)
        for (level, expected), row in zip(cases, walker, strict=True):
            with self.subTest(level=level):
                self.assertEqual(("x", [(expected, 1)]), typing.cast("urwid.Text", row).get_text())

    def test_severity_attr_and_follow_end(self) -> None:
        walker = urwid.SimpleFocusDequeWalker([], maxlen=2, follow_end=True)
        handler = log_handler.ListWalkerHandler(walker, loop=self.loop, severity_attr={urwid.Severity.ERROR: "error"})
        self.addCleanup(handler.close)
        logger = logging.getLogger(f"tests.log_handler.{self.id()}")
        logger.propagate = False
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        listbox = urwid.ListBox(walker)
        self.start()
        logger.warning("plain")
        self.event_loop.advance(0)
        listbox.render((20, 1))
        logger.error("first error")
        logger.error("second error")
        self.event_loop.advance(0)
        self.assertEqual(["first error", "second error"], self.shown(handler))
        self.assertEqual(("second error", [("error", 12)]), typing.cast("urwid.Text", walker[1]).get_text())
        self.assertEqual(1, listbox.focus_position)
        self.assertEqual(urwid.testing.render_text(listbox, (20, 1), strip=True), ["second error"])

    def test_invalid_severity_attr(self) -> None:
        for description, severity_attr in (
            ("int key", {3: "error"}),
            ("attribute map value", {urwid.Severity.ERROR: {None: "error"}}),
        ):
            with self.subTest(description), self.assertRaises(TypeError):
                self.make_handler(self.loop, severity_attr=severity_attr)

    def test_plain_row_without_attr(self) -> None:
        handler, logger = self.handler(severity_attr={urwid.Severity.ERROR: "error"})
        self.start()
        logger.warning("plain")
        self.event_loop.advance(0)
        walker = self.walker(handler)
        self.assertEqual(("plain", []), typing.cast("urwid.Text", walker[0]).get_text())

    def test_feedback_from_a_redraw_settles(self) -> None:
        """With the root logger at DEBUG, a widget callback that logs to an urwid logger does not loop."""
        handler = self.make_handler(self.loop)
        self.addCleanup(handler.close)
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        self.on_show(handler, lambda: logging.getLogger("urwid.display").debug("Drawing screen"))
        self.start()
        logging.getLogger(f"tests.log_handler.{self.id()}").info("one")
        self.event_loop.advance(0)
        self.assertEqual(["one"], self.shown(handler))
        self.assertEqual(0, len(handler._pending))


class NotificationsHandlerTest(_HandlerTests, unittest.TestCase):
    def make_handler(self, loop: urwid.MainLoop, **kwargs: typing.Any) -> log_handler.NotificationsHandler:
        return log_handler.NotificationsHandler(urwid.Notifications(timeout=None), loop=loop, **kwargs)

    def shown(self, handler: log_handler._LoopHandler) -> list[str]:
        assert isinstance(handler, log_handler.NotificationsHandler)
        return [notification.widget.text for notification in handler.notifications.notifications]

    def on_show(self, handler: log_handler._LoopHandler, callback: Callable[[], None]) -> None:
        assert isinstance(handler, log_handler.NotificationsHandler)
        urwid.connect_signal(handler.notifications, "change", lambda _widget: callback())

    def test_level_to_severity(self) -> None:
        handler, logger = self.handler()
        cases = [
            (logging.DEBUG, urwid.Severity.DEBUG),
            (logging.INFO, urwid.Severity.INFO),
            (logging.WARNING, urwid.Severity.WARNING),
            (logging.ERROR, urwid.Severity.ERROR),
            (logging.CRITICAL, urwid.Severity.CRITICAL),
            (logging.INFO + 5, urwid.Severity.INFO),
            (logging.DEBUG - 5, urwid.Severity.DEBUG),
        ]
        for level, _expected in cases:
            logger.log(level, "x")
        self.start()
        handler.resume()
        self.event_loop.advance(0)
        notifications = typing.cast("log_handler.NotificationsHandler", handler).notifications.notifications
        for (level, expected), notification in zip(cases, notifications, strict=True):
            with self.subTest(level=level):
                self.assertIs(expected, notification.severity)

    def test_timeout(self) -> None:
        for description, widget_timeout, kwargs, expected in (
            ("widget's own", 5, {}, 5),
            ("given", 5, {"timeout": 2}, 2),
            ("kept", 5, {"timeout": None}, None),
        ):
            with self.subTest(description):
                event_loop = VirtualClockEventLoop()
                loop = self.new_loop(event_loop)
                notifications = urwid.Notifications(timeout=widget_timeout)
                handler = log_handler.NotificationsHandler(notifications, loop=loop, **kwargs)
                logger = logging.getLogger(f"tests.log_handler.{self.id()}.{description}")
                logger.propagate = False
                logger.setLevel(logging.INFO)
                logger.addHandler(handler)
                try:
                    self.start(loop)
                    logger.info("message")
                    event_loop.advance(0)
                    self.assertEqual(1, len(notifications.notifications))
                    self.assertEqual(expected, notifications.notifications[0].timeout)
                    if expected is not None:
                        event_loop.advance(expected)
                        self.assertEqual((), notifications.notifications)
                finally:
                    logger.removeHandler(handler)
                    handler.close()
                    loop.stop()

    def test_invalid_arguments(self) -> None:
        other = self.new_loop(VirtualClockEventLoop())
        for description, notifications, kwargs, error in (
            ("bound to another loop", urwid.Notifications(loop=other), {}, ValueError),
            ("zero timeout", urwid.Notifications(), {"timeout": 0}, ValueError),
            ("str timeout", urwid.Notifications(), {"timeout": "5"}, TypeError),
        ):
            with self.subTest(description), self.assertRaises(error):
                log_handler.NotificationsHandler(notifications, loop=self.loop, **kwargs)
        log_handler.NotificationsHandler(urwid.Notifications(loop=self.loop), loop=self.loop).close()

    def test_feedback_from_alarm_settles(self) -> None:
        """With the root logger at DEBUG, the DEBUG record of the message's alarm is not shown."""
        notifications = urwid.Notifications(timeout=5)
        handler = log_handler.NotificationsHandler(notifications, loop=self.loop)
        self.addCleanup(handler.close)
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        self.start()
        logging.getLogger(f"tests.log_handler.{self.id()}").info("one")
        self.event_loop.advance(0)
        self.assertEqual(["one"], self.shown(handler))
        self.assertEqual(0, len(handler._pending))


if __name__ == "__main__":
    unittest.main()
