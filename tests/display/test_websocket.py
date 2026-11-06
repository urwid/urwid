"""Tests for the WebSocket display, through a fake transport and a fake event loop."""

from __future__ import annotations

import json
import re
import threading
import typing
import unittest
from unittest import mock

import urwid
from urwid.display import websocket

if typing.TYPE_CHECKING:
    from collections.abc import Callable


class FakeTransport:
    """Records what a screen sends and whether it closed the connection."""

    def __init__(self) -> None:
        """Start with nothing sent and the connection open."""
        self.sent: list[str] = []
        self.close_count = 0

    def send(self, text: str) -> None:
        """Record *text* as sent."""
        self.sent.append(text)

    def close(self) -> None:
        """Count one close."""
        self.close_count += 1


class FakeEventLoop:
    """Event loop that runs its alarms and idle callbacks only when the test asks."""

    def __init__(self) -> None:
        """Start with nothing scheduled."""
        self.alarms: dict[int, Callable[[], typing.Any]] = {}
        self.idle: dict[int, Callable[[], typing.Any]] = {}
        self.files: dict[int, Callable[[], typing.Any]] = {}
        self._handle = 0

    def _next(self) -> int:
        self._handle += 1
        return self._handle

    def alarm(self, seconds: float, callback: Callable[[], typing.Any]) -> int:
        """Schedule *callback* for the next :meth:`run_pending`, whatever *seconds* is."""
        handle = self._next()
        self.alarms[handle] = callback
        return handle

    def remove_alarm(self, handle: int) -> bool:
        """Cancel an alarm and return whether it was pending."""
        return self.alarms.pop(handle, None) is not None

    def enter_idle(self, callback: Callable[[], typing.Any]) -> int:
        """Run *callback* at the end of every :meth:`run_pending`."""
        handle = self._next()
        self.idle[handle] = callback
        return handle

    def remove_enter_idle(self, handle: int) -> bool:
        """Remove an idle callback and return whether it was registered."""
        return self.idle.pop(handle, None) is not None

    def watch_file(self, fd: int, callback: Callable[[], typing.Any]) -> int:
        """Record a watch that never fires."""
        handle = self._next()
        self.files[handle] = callback
        return handle

    def remove_watch_file(self, handle: int) -> bool:
        """Remove a watch and return whether it was registered."""
        return self.files.pop(handle, None) is not None

    def run_pending(self) -> None:
        """Run the due alarms, then the idle callbacks, the way an event loop iteration does."""
        alarms, self.alarms = self.alarms, {}
        for callback in alarms.values():
            callback()
        for callback in list(self.idle.values()):
            callback()


def key(name: str) -> str:
    """Return the message the page sends for the key *name*."""
    return json.dumps({"type": "key", "key": name})


def resize(cols: object, rows: object) -> str:
    """Return the message the page sends for a window of *cols* by *rows*."""
    return json.dumps({"type": "resize", "cols": cols, "rows": rows})


class FeedTest(unittest.TestCase):
    """Checking and queueing the messages from the page."""

    def setUp(self) -> None:
        """Create an unstarted screen with the default size."""
        self.transport = FakeTransport()
        self.screen = websocket.Screen(self.transport)

    def test_accepts_the_keys_the_page_script_sends(self) -> None:
        """Every key name the page script can send is queued as it is."""
        # a no-break space (macOS Option+Space) and a private-use character (the Apple logo) are typed keys too
        names = [
            "a",
            "A",
            " ",
            "é",
            "\u00a0",
            "meta \u00a0",
            "\uf8ff",
            "enter",
            "page up",
            "f12",
            "ctrl a",
            "ctrl  ",
            "shift meta ctrl tab",
        ]
        for name in names:
            self.screen.feed(key(name))
        self.assertEqual(names, self.screen._pending)

    def test_resize_sets_the_size_and_queues_a_window_resize(self) -> None:
        """A resize message changes the size and queues the key the main loop redraws on."""
        self.screen.feed(resize(100, 30))
        self.assertEqual((100, 30), self.screen.get_cols_rows())
        self.assertEqual(["window resize"], self.screen._pending)

    def test_resize_is_limited_to_the_maximum_size(self) -> None:
        """A size above the limits is reduced to them."""
        self.screen.feed(resize(10**50, 10**6))
        self.assertEqual((websocket.MAX_COLS, websocket.MAX_ROWS), self.screen.get_cols_rows())

    def test_rejects_invalid_messages(self) -> None:
        """A message outside the protocol raises and changes nothing."""
        invalid = {
            "binary": b'{"type": "key", "key": "a"}',
            "too long": json.dumps({"type": "key", "key": "a", "pad": "x" * websocket.MAX_MESSAGE_LENGTH}),
            "not JSON": "a",
            "NaN": '{"type": "resize", "cols": NaN, "rows": 1}',
            "array": '["key", "a"]',
            "unknown type": json.dumps({"type": "paste", "text": "a"}),
            "extra key": json.dumps({"type": "key", "key": "a", "repeat": 2}),
            "missing key": json.dumps({"type": "key"}),
            "key not a string": json.dumps({"type": "key", "key": 1}),
            "unknown key name": key("rm -rf"),
            "two characters": key("ab"),
            "control character": key("\x1b"),
            "lone surrogate": '{"type": "key", "key": "\\ud800"}',
            "modifier only": key("ctrl "),
            "modifiers out of order": key("ctrl shift a"),
            "empty key": key(""),
            "boolean size": resize(True, 3),
            "zero size": resize(0, 3),
            "negative size": resize(5, -1),
            "fractional size": resize(80.5, 24),
            "string size": resize("80", 24),
        }
        for label, message in invalid.items():
            with self.subTest(label), self.assertRaises(websocket.InvalidMessageError):
                self.screen.feed(message)
        self.assertEqual([], self.screen._pending)
        self.assertEqual((80, 24), self.screen.get_cols_rows())

    def test_rejects_input_beyond_the_pending_limit(self) -> None:
        """A page that floods the screen with input is refused."""
        for _ in range(websocket.MAX_PENDING_INPUT):
            self.screen.feed(key("a"))
        with self.assertRaises(websocket.InvalidMessageError):
            self.screen.feed(key("a"))

    def test_ignores_messages_after_close(self) -> None:
        """A closed session takes no input and closes its transport once."""
        self.screen.close()
        self.screen.close()
        self.screen.feed("not even JSON")
        self.assertEqual([], self.screen._pending)
        self.assertEqual(1, self.transport.close_count)
        self.assertTrue(self.screen.closed)

    def test_size_given_to_the_constructor_must_be_positive(self) -> None:
        """The initial size is checked."""
        with self.assertRaises(ValueError):
            websocket.Screen(self.transport, cols=0)


class DrawTest(unittest.TestCase):
    """The rows sent to the page."""

    def setUp(self) -> None:
        """Start a screen of 5 by 2 characters."""
        self.transport = FakeTransport()
        self.screen = websocket.Screen(self.transport, cols=5, rows=2)
        self.screen.register_palette_entry("link", "light blue", "black")
        self.screen.start()
        self.addCleanup(self.screen.stop)

    def test_sends_rows_then_references_to_unchanged_rows(self) -> None:
        """An unchanged row is sent as a reference to the row the page shows."""
        canvas = urwid.Text("ab\ncd").render((5,))
        self.screen.draw_screen((5, 2), canvas)
        self.screen.draw_screen((5, 2), canvas)
        style = "color:#000000;background-color:#e5e5e5"
        self.assertEqual(
            [f"{style}\x01ab   \n\n{style}\x01cd   \n\n", "<0\n<1\n"],
            self.transport.sent,
        )

    def test_clear_and_restart_send_every_row_again(self) -> None:
        """clear() and a restart make the next draw send every row."""
        canvas = urwid.Text("ab").render((5,))
        self.screen.draw_screen((5, 1), canvas)
        self.screen.clear()
        self.screen.draw_screen((5, 1), canvas)
        self.screen.stop()
        self.screen.start()
        self.screen.draw_screen((5, 1), canvas)
        self.assertEqual(3, len(self.transport.sent))
        self.assertEqual(1, len(set(self.transport.sent)))
        self.assertNotIn("<", self.transport.sent[0])

    def test_link_with_an_unsafe_scheme_is_sent_as_text(self) -> None:
        """Only a link with a scheme a browser may follow reaches the page."""
        unsafe = urwid.AttrSpec("default", "default", hyperlink=urwid.Hyperlink("javascript:alert(1)"))
        safe = urwid.AttrSpec("default", "default", hyperlink=urwid.Hyperlink("https://urwid.org"))
        canvas = urwid.Text([(unsafe, "x"), (safe, "y")]).render((5,))
        self.screen.draw_screen((5, 1), canvas)
        self.assertNotIn("javascript", self.transport.sent[0])
        self.assertIn("\x01https://urwid.org\x01y", self.transport.sent[0])

    def test_control_characters_do_not_reach_the_page(self) -> None:
        """A control character in a canvas cannot forge a field separator."""
        # a canvas, since a Text widget already leaves control characters out
        self.screen.draw_screen((5, 1), urwid.TextCanvas([b"a\x01b  "]))
        self.assertIn("\x01a?b", self.transport.sent[0])
        self.assertEqual(1, self.transport.sent[0].count("\x01"))

    def test_draws_nothing_after_close(self) -> None:
        """A closed session sends nothing."""
        self.screen.close()
        self.screen.draw_screen((5, 1), urwid.Text("ab").render((5,)))
        self.assertEqual([], self.transport.sent)


class SessionsTest(unittest.TestCase):
    """Several sessions, each a screen and a main loop, on one event loop."""

    def setUp(self) -> None:
        """Start two sessions with an Edit each, each closing on an error of its own, and draw them once."""
        self.event_loop = FakeEventLoop()
        self.sessions: list[tuple[FakeTransport, websocket.Screen, urwid.Edit, urwid.MainLoop]] = []
        self.errors: list[tuple[int, Exception]] = []
        for number in range(2):
            transport = FakeTransport()
            screen = websocket.Screen(transport, cols=20, rows=1)
            edit = urwid.Edit()

            def on_error(exc: Exception, number: int = number, screen: websocket.Screen = screen) -> None:
                self.errors.append((number, exc))
                screen.close()

            guarded = urwid.GuardedEventLoop(self.event_loop, on_error)
            loop = urwid.MainLoop(urwid.Filler(edit), screen=screen, event_loop=guarded)
            loop.start()
            self.addCleanup(loop.stop)
            self.sessions.append((transport, screen, edit, loop))
        self.event_loop.run_pending()

    def test_input_reaches_only_its_own_session(self) -> None:
        """Keys fed to one screen reach only that session's widgets."""
        first_transport, first_screen, first_edit, _ = self.sessions[0]
        second_transport, _, second_edit, _ = self.sessions[1]
        first_transport.sent.clear()
        second_transport.sent.clear()

        first_screen.feed(key("h"))
        first_screen.feed(key("i"))
        self.event_loop.run_pending()

        self.assertEqual("hi", first_edit.edit_text)
        self.assertEqual("", second_edit.edit_text)
        self.assertEqual(1, len(first_transport.sent))
        self.assertIn("hi", first_transport.sent[0])
        # the second session's rows are unchanged, so its redraw only refers to them
        self.assertEqual(["<0\n"], second_transport.sent)

    def test_resize_redraws_at_the_new_size(self) -> None:
        """A resize message makes the main loop redraw at the new size."""
        transport, screen, _, _ = self.sessions[0]
        transport.sent.clear()
        screen.feed(resize(10, 3))
        self.event_loop.run_pending()
        self.assertEqual(3, transport.sent[-1].count("\n\n"))

    def test_exit_main_loop_closes_only_its_own_session(self) -> None:
        """ExitMainLoop from an input handler closes its own session, and the other one goes on."""
        first_transport, first_screen, _, first_loop = self.sessions[0]
        second_transport, second_screen, _, _ = self.sessions[1]

        def quit_on_q(pressed: str | tuple[str, int, int, int]) -> None:
            if pressed == "esc":
                raise urwid.ExitMainLoop

        first_loop._unhandled_input = quit_on_q
        first_screen.feed(key("esc"))
        self.event_loop.run_pending()

        self.assertEqual(1, first_transport.close_count)
        self.assertTrue(first_screen.closed)
        self.assertEqual(0, second_transport.close_count)
        second_screen.feed(key("x"))
        self.event_loop.run_pending()
        self.assertIn("x", second_transport.sent[-1])

    def test_exit_main_loop_from_an_alarm_closes_only_its_own_session(self) -> None:
        """ExitMainLoop raised by one application's alarm closes that session, and the other one goes on.

        MainLoop logs any other exception from an alarm itself, so ExitMainLoop is the one that reaches the loop.
        """
        first_transport, first_screen, _, first_loop = self.sessions[0]
        second_transport, second_screen, second_edit, _ = self.sessions[1]

        def stop(_loop: urwid.MainLoop, _data: object) -> None:
            raise urwid.ExitMainLoop

        first_loop.set_alarm_in(1, stop)
        self.event_loop.run_pending()

        self.assertEqual([0], [number for number, _error in self.errors])
        self.assertIsInstance(self.errors[0][1], urwid.ExitMainLoop)
        self.assertEqual(1, first_transport.close_count)
        self.assertTrue(first_screen.closed)
        self.assertFalse(second_screen.closed)
        second_screen.feed(key("y"))
        self.event_loop.run_pending()
        self.assertEqual("y", second_edit.edit_text)
        self.assertIn("y", second_transport.sent[-1])

    def test_render_error_closes_only_its_own_session(self) -> None:
        """An exception while one application redraws closes that session, and the other one still redraws."""
        _, first_screen, _, first_loop = self.sessions[0]
        second_transport, second_screen, _, _ = self.sessions[1]
        first_loop.widget = urwid.Filler(urwid.Text("x"))
        error = RuntimeError("render")
        with mock.patch.object(urwid.Text, "render", side_effect=error):
            first_screen.feed(key("a"))
            second_screen.feed(key("b"))
            self.event_loop.run_pending()

        self.assertEqual(0, self.errors[0][0])
        self.assertIs(error, self.errors[0][1])
        self.assertTrue(first_screen.closed)
        self.assertFalse(second_screen.closed)
        self.assertIn("b", second_transport.sent[-1])

    def test_input_waits_while_the_screen_is_unhooked(self) -> None:
        """Input fed while the main loop is stopped is handled once it starts again."""
        _transport, screen, edit, loop = self.sessions[0]
        loop.stop()
        screen.feed(key("z"))
        self.event_loop.run_pending()
        self.assertEqual("", edit.edit_text)

        loop.start()
        self.event_loop.run_pending()
        self.assertEqual("z", edit.edit_text)


class SharedSelectLoopTest(unittest.TestCase):
    """Two guarded sessions on one real event loop, where call_from_thread wakes the loop through a socket."""

    def test_exit_main_loop_from_call_from_thread_closes_only_its_own_session(self) -> None:
        """ExitMainLoop raised by a call from another thread reaches the session's handler, and the loop goes on."""
        event_loop = urwid.SelectEventLoop()
        errors: list[tuple[int, str]] = []
        screens: list[websocket.Screen] = []
        loops: list[urwid.MainLoop] = []
        for number in range(2):
            screen = websocket.Screen(FakeTransport(), cols=20, rows=1)

            def on_error(exc: Exception, number: int = number, screen: websocket.Screen = screen) -> None:
                errors.append((number, type(exc).__name__))
                screen.close()

            loop = urwid.MainLoop(
                urwid.Filler(urwid.Text("")),
                screen=screen,
                event_loop=urwid.GuardedEventLoop(event_loop, on_error),
            )
            loop.start()
            self.addCleanup(loop.stop)
            screens.append(screen)
            loops.append(loop)

        ran: list[int] = []

        def stop_session() -> None:
            ran.append(0)
            raise urwid.ExitMainLoop

        def from_thread() -> None:
            loops[0].call_from_thread(stop_session)
            loops[1].call_from_thread(ran.append, 1)

        def end_run() -> None:
            raise urwid.ExitMainLoop

        thread = threading.Thread(target=from_thread)
        thread.start()
        thread.join(timeout=5)
        # registered on the unguarded loop, so it ends the run; it also ends the test if a call never arrives
        event_loop.alarm(0.2, end_run)
        event_loop.run()

        self.assertEqual([0, 1], sorted(ran))
        self.assertEqual([(0, "ExitMainLoop")], errors)
        self.assertTrue(screens[0].closed)
        self.assertFalse(screens[1].closed)


class PageTest(unittest.TestCase):
    """The page and the files it loads."""

    def test_page_escapes_its_arguments_and_has_no_inline_code(self) -> None:
        """The page escapes the title and the WebSocket path and carries no inline script or style."""
        page = websocket.html_page('<script>"', '"><script>')
        self.assertNotIn("<script>", page.replace("<script src=", ""))
        self.assertNotIn("style=", page)
        self.assertIsNone(re.search(r"\son\w+\s*=", page, re.IGNORECASE))
        self.assertIn("&lt;script&gt;&quot;", page)

    def test_page_loads_exactly_the_static_files(self) -> None:
        """The page names every static file, and every static file exists."""
        page = websocket.html_page("t", "ws")
        for name, static in websocket.STATIC_FILES.items():
            with self.subTest(name):
                self.assertIn(f'"{name}"', page)
                self.assertTrue(static.read())

    def test_page_script_has_no_dynamic_code(self) -> None:
        """The page script builds no code or markup from strings."""
        for name in ("web_common.js", "websocket.js"):
            source = websocket.STATIC_FILES[name].read().decode("utf-8")
            for construct in ("eval(", "innerHTML", "outerHTML", "document.write", "new Function", "setAttribute("):
                with self.subTest(name=name, construct=construct):
                    self.assertNotIn(construct, source)
