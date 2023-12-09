from __future__ import annotations

import asyncio
import os
import socket
import sys
import typing
import unittest

import urwid

if typing.TYPE_CHECKING:
    from types import TracebackType

IS_WINDOWS = os.name == "nt"


class ClosingSocketPair(typing.ContextManager[typing.Tuple[socket.socket, socket.socket]]):
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


class SelectEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.SelectEventLoop()


try:
    import gi.repository
except ImportError:
    pass
else:

    class GLibEventLoopTest(unittest.TestCase, EventLoopTestMixin):
        def setUp(self):
            self.evl = urwid.GLibEventLoop()

        def test_error(self):
            evl = self.evl
            evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
            self.assertRaises(ZeroDivisionError, evl.run)


try:
    import tornado
except ImportError:
    pass
else:

    @unittest.skipIf(
        IS_WINDOWS,
        "Windows is temporary not supported by TornadoEventLoop due to race conditions.",
    )
    class TornadoEventLoopTest(unittest.TestCase, EventLoopTestMixin):
        def setUp(self):
            from tornado.ioloop import IOLoop

            self.evl = urwid.TornadoEventLoop(IOLoop())

        _expected_idle_handle = None


try:
    import twisted
except ImportError:
    pass
else:

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
                self.assertEqual(evl.enter_idle(say_waiting), 1)
                evl.run()

            self.assertTrue("da" in out, out)
            self.assertTrue("ta" in out, out)
            self.assertTrue("hello" in out, out)
            self.assertTrue("remove_alarm ok" in out, out)
            self.assertTrue("clean exit" in out, out)

        def test_error(self):
            evl = self.evl
            evl.alarm(0, lambda: 1 / 0)  # Simulate error in event loop
            self.assertRaises(ZeroDivisionError, evl.run)


@unittest.skipIf(IS_WINDOWS, "Windows is temporary not supported by AsyncioEventLoop.")
class AsyncioEventLoopTest(unittest.TestCase, EventLoopTestMixin):
    def setUp(self):
        self.evl = urwid.AsyncioEventLoop()

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

        asyncio.ensure_future(error_coro(), loop=asyncio.get_event_loop_policy().get_event_loop())
        self.assertRaises(ZeroDivisionError, evl.run)


try:
    import trio
except ImportError:
    pass
else:

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


try:
    import zmq
except ImportError:
    pass
else:

    @unittest.skipIf(IS_WINDOWS, "ZMQEventLoop is not supported under windows")
    class ZMQEventLoopTest(unittest.TestCase, EventLoopTestMixin):
        def setUp(self):
            self.evl = urwid.ZMQEventLoop()
