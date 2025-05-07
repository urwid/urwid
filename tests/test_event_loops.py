from __future__ import annotations

import asyncio
import concurrent.futures
import socket
import sys
import typing
import unittest

import urwid

if typing.TYPE_CHECKING:
    from concurrent.futures import Future
    from types import TracebackType

try:
    import gi.repository
except ImportError:
    GLIB_AVAILABLE = False
else:
    GLIB_AVAILABLE = True

try:
    import tornado
except ImportError:
    TORNADO_AVAILABLE = False
else:
    TORNADO_AVAILABLE = True

try:
    import twisted
except ImportError:
    TWISTED_AVAILABLE = False
else:
    TWISTED_AVAILABLE = True

try:
    import trio
except ImportError:
    TRIO_AVAILABLE = False
else:
    TRIO_AVAILABLE = True

try:
    import zmq
except ImportError:
    ZMQ_AVAILABLE = False
else:
    ZMQ_AVAILABLE = True

IS_WINDOWS = sys.platform == "win32"


class ClosingSocketPair(typing.ContextManager[tuple[socket.socket, socket.socket]]):
    __slots__ = ("rd_s", "wr_s")

    def __init__(self) -> None:
        self.rd_s: socket.socket | None = None
        self.wr_s: socket.socket | None = None

    def __enter__(self) -> tuple[socket.socket, socket.socket]:
        self.rd_s, self.wr_s = socket.socketpair()
        return self.rd_s, self.wr_s

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.rd_s is not None:
            self.rd_s.close()
        if self.wr_s is not None:
            self.wr_s.close()


class EventLoopTestMixin:
    evl: urwid.EventLoop

    def test_event_loop(self):
        evl: urwid.EventLoop = self.evl
        out = []
        rd: socket.socket
        wr: socket.socket

        def step1():
            out.append("writing")
            wr.send(b"hi")

        def step2():
            out.append(rd.recv(2).decode("ascii"))
            raise urwid.ExitMainLoop

        with ClosingSocketPair() as (rd, wr):
            _handle = evl.alarm(0, step1)
            _handle = evl.watch_file(rd.fileno(), step2)

            evl.run()

        self.assertEqual(out, ["writing", "hi"])

    def test_remove_alarm(self):
        evl: urwid.EventLoop = self.evl
        handle = evl.alarm(50, lambda: None)

        def step1():
            self.assertTrue(evl.remove_alarm(handle))
            self.assertFalse(evl.remove_alarm(handle))
            raise urwid.ExitMainLoop

        evl.alarm(0, step1)
        evl.run()

    def test_remove_watch_file(self):
        evl: urwid.EventLoop = self.evl

        with ClosingSocketPair() as (rd, _wr):
            handle = evl.watch_file(rd.fileno(), lambda: None)

            def step1():
                self.assertTrue(evl.remove_watch_file(handle))
                self.assertFalse(evl.remove_watch_file(handle))
                raise urwid.ExitMainLoop

            evl.alarm(0, step1)
            evl.run()

    _expected_idle_handle = 1

    def test_run(self):
        evl: urwid.EventLoop = self.evl
        out = []
        wr: socket.socket
        rd: socket.socket

        def say_hello():
            out.append("hello")

        def say_waiting():
            out.append("waiting")

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def exit_error() -> typing.NoReturn:
            1 / 0

        with ClosingSocketPair() as (rd, wr):
            self.assertEqual(wr.send(b"data"), 4)

            _handle = evl.alarm(0.01, exit_clean)
            _handle = evl.alarm(0.005, say_hello)
            idle_handle = evl.enter_idle(say_waiting)
            if self._expected_idle_handle is not None:
                self.assertEqual(idle_handle, 1)

            evl.run()
            self.assertTrue("waiting" in out, out)
            self.assertTrue("hello" in out, out)
            self.assertTrue("clean exit" in out, out)
            handle = evl.watch_file(rd.fileno(), exit_clean)
            del out[:]

            evl.run()
            self.assertEqual(["clean exit"], out)
            self.assertTrue(evl.remove_watch_file(handle))
            _handle = evl.alarm(0, exit_error)
            self.assertRaises(ZeroDivisionError, evl.run)
            _handle = evl.watch_file(rd.fileno(), exit_error)
            self.assertRaises(ZeroDivisionError, evl.run)

    def test_run_in_executor(self):
        out: list[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:

            def start():
                out.append("started")
                self.evl.run_in_executor(executor, func).add_done_callback(callback)

            def func() -> bool:
                out.append("future called")
                return True

            def callback(fut: Future) -> None:
                out.append(f"callback called with future outcome: {fut.result()}")

            def exit_clean() -> typing.NoReturn:
                out.append("clean exit")
                raise urwid.ExitMainLoop

            _handle = self.evl.alarm(0.1, exit_clean)
            _handle = self.evl.alarm(0.005, start)
            self.evl.run()

        self.assertEqual(
            [
                "started",
                "future called",
                "callback called with future outcome: True",
                "clean exit",
            ],
            out,
        )


class SelectEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.SelectEventLoop()


@unittest.skipIf(IS_WINDOWS, "Windows is temporary not supported by AsyncioEventLoop.")
class AsyncioEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        if sys.version_info[:2] < (3, 11):
            self.loop = asyncio.get_event_loop_policy().get_event_loop()
            self.evl_runner = None
        else:
            self.evl_runner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
            self.loop = self.evl_runner.get_loop()
        self.evl = urwid.AsyncioEventLoop(loop=self.loop)

    def tearDown(self):
        if self.evl_runner is not None:
            self.evl_runner.close()

    _expected_idle_handle = None

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    @unittest.skipIf(
        sys.implementation.name == "pypy",
        "Well known dead wait (lock?) on pypy.",
    )
    def test_coroutine_error(self):
        evl = self.evl

        async def error_coro():
            result = 1 / 0  # Simulate error in coroutine
            return result

        asyncio.ensure_future(error_coro(), loop=self.loop)
        self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skipUnless(GLIB_AVAILABLE, "GLIB unavailable")
class GLibEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.GLibEventLoop()

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skipUnless(TORNADO_AVAILABLE, "Tornado not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TornadoEventLoop due to race conditions.",
)
class TornadoEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        from tornado.ioloop import IOLoop

        self.evl = urwid.TornadoEventLoop(IOLoop())

    _expected_idle_handle = None


@unittest.skipUnless(TWISTED_AVAILABLE, "Twisted is not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TwistedEventLoop due to race conditions.",
)
class TwistedEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.TwistedEventLoop()

    # can't restart twisted reactor, so use shortened tests
    def test_event_loop(self):
        pass

    def test_remove_alarm(self):
        pass

    def test_remove_watch_file(self):
        pass

    def test_run(self):
        from twisted.internet import threads

        evl = self.evl
        out = []
        wr: socket.socket
        rd: socket.socket

        def step2():
            out.append(rd.recv(2).decode("ascii"))

        def say_hello():
            out.append("hello")

        def say_waiting():
            out.append("waiting")

        def test_remove_alarm():
            handle = evl.alarm(50, lambda: None)
            self.assertTrue(evl.remove_alarm(handle))
            self.assertFalse(evl.remove_alarm(handle))
            out.append("remove_alarm ok")

        def test_remove_watch_file():
            with ClosingSocketPair() as (rd_, _wr):
                handle = evl.watch_file(rd_.fileno(), lambda: None)
                self.assertTrue(evl.remove_watch_file(handle))
                self.assertFalse(evl.remove_watch_file(handle))

            out.append("remove_watch_file ok")

        def test_threaded():
            out.append("schedule to thread")
            threads.deferToThread(func).addCallback(callback)

        def func() -> bool:
            out.append("future called")
            return True

        def callback(result: bool) -> None:
            out.append(f"callback called with future outcome: {result}")

        def exit_clean() -> typing.NoReturn:
            out.append("clean exit")
            raise urwid.ExitMainLoop

        def exit_error() -> typing.NoReturn:
            1 / 0

        with ClosingSocketPair() as (rd, wr):
            self.assertEqual(wr.send(b"data"), 4)

            _handle = evl.watch_file(rd.fileno(), step2)
            _handle = evl.alarm(0.1, exit_clean)
            _handle = evl.alarm(0.05, say_hello)
            _handle = evl.alarm(0.06, test_remove_alarm)
            _handle = evl.alarm(0.07, test_remove_watch_file)
            _handle = evl.alarm(0.08, test_threaded)
            self.assertEqual(evl.enter_idle(say_waiting), 1)
            evl.run()

        self.assertIn("da", out)
        self.assertIn("ta", out)
        self.assertIn("hello", out)
        self.assertIn("remove_alarm ok", out)
        self.assertIn("clean exit", out)
        self.assertIn("schedule to thread", out)
        self.assertIn("future called", out)
        self.assertIn("callback called with future outcome: True", out)

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    @unittest.skip("not implemented for twisted event loop")
    def test_run_in_executor(self):
        """Not implemented for twisted event loop."""


@unittest.skipUnless(TRIO_AVAILABLE, "Trio not available")
@unittest.skipIf(
    IS_WINDOWS,
    "Windows is temporary not supported by TrioEventLoop due to race conditions.",
)
class TrioEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.TrioEventLoop()

    _expected_idle_handle = None

    def test_error(self):
        evl = self.evl
        evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
        self.assertRaises(ZeroDivisionError, evl.run)

    @unittest.skip("not implemented for trio event loop")
    def test_run_in_executor(self):
        """Not implemented for trio event loop."""


@unittest.skipUnless(ZMQ_AVAILABLE, "ZMQ is not available")
@unittest.skipIf(IS_WINDOWS, "ZMQEventLoop is not supported under windows")
class ZMQEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.ZMQEventLoop()
