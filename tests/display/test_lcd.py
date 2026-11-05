from __future__ import annotations

import socket
import time
import typing
import unittest
import warnings
from unittest import mock

import urwid
from urwid.display import lcd

if typing.TYPE_CHECKING:
    from collections.abc import Callable

try:
    import serial
except ImportError:
    serial = None


def packet(command: int, data: bytes = b"") -> bytes:
    """Return a device packet: command, length, data and CRC."""
    body = bytes([command, len(data), *data])
    return body + lcd.CFLCDScreen.get_crc(body)


class SocketSerial:
    """Stand-in for a non-blocking ``serial.Serial`` port, backed by one end of a socket pair."""

    def __init__(self, sock: socket.socket) -> None:
        """Use *sock* as the port; the test keeps the other end as the device."""
        self._sock = sock
        self._sock.setblocking(False)

    def read(self, size: int = 1) -> bytes:
        """Return up to *size* bytes the device sent, or ``b""`` when none are waiting, as ``timeout=0`` does."""
        try:
            return self._sock.recv(size)
        except BlockingIOError:
            return b""

    def write(self, data: bytes) -> int:
        """Send *data* to the device."""
        return self._sock.send(data)

    def fileno(self) -> int:
        """Return the descriptor the event loop watches."""
        return self._sock.fileno()


@unittest.skipIf(serial is None, "pyserial is only installed with the serial extra")
class CF635ScreenTest(unittest.TestCase):
    def test_input_descriptor_is_the_open_port_fileno(self) -> None:
        """Watch the descriptor the open serial port reports through fileno()."""
        with mock.patch.object(serial, "Serial") as serial_cls, self.assertWarns(DeprecationWarning):
            serial_cls.return_value.fileno.return_value = 7
            screen = lcd.CF635Screen("/dev/ttyUSB0")

        self.assertEqual([7], screen.get_input_descriptors())

    def test_deprecated_once_per_screen(self) -> None:
        """A screen warns once that the LCD display module is deprecated.

        The key repeat helper warns only when an application builds it, not when the screen does.
        """
        suffix = "Deprecated since urwid 5.1.0, will be removed in version 6.0."
        with (
            mock.patch.object(serial, "Serial"),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            screen = lcd.CF635Screen("/dev/ttyUSB0")
            lcd.KeyRepeatSimulator(0.5, 0.125)

        self.assertEqual(
            [
                (DeprecationWarning, f"CF635Screen is deprecated with the LCD display module. {suffix}"),
                (DeprecationWarning, f"KeyRepeatSimulator is deprecated with the LCD display module. {suffix}"),
            ],
            [(warning.category, str(warning.message)) for warning in caught],
        )
        self.assertEqual({__file__}, {warning.filename for warning in caught})
        self.assertIsInstance(screen.key_repeat, lcd.KeyRepeatSimulator)

    def test_application_subclass_is_warned_under_the_urwid_class(self) -> None:
        """A subclass an application defines is warned about under the name of the urwid class it builds on."""

        class Panel(lcd.CF635Screen):
            """An application's own screen class."""

        with mock.patch.object(serial, "Serial"), self.assertWarnsRegex(DeprecationWarning, "^CF635Screen is"):
            Panel("/dev/ttyUSB0")

    def _screen(self, **kwargs: typing.Any) -> tuple[lcd.CF635Screen, socket.socket]:
        """Return a screen on a fake serial port, and the device's end of that port."""
        port, device = socket.socketpair()
        self.addCleanup(port.close)
        self.addCleanup(device.close)
        device.settimeout(1)  # a test reading what was never sent fails instead of waiting
        with mock.patch.object(serial, "Serial", return_value=SocketSerial(port)), self.assertWarns(DeprecationWarning):
            return lcd.CF635Screen("/dev/ttyUSB0", **kwargs), device

    def _run(
        self,
        screen: lcd.CF635Screen,
        keys: list[str],
        count: int,
        *,
        alarm: Callable[[], object] | None = None,
    ) -> urwid.MainLoop:
        """Run a main loop on *screen* until *count* keys reached *keys*, or a second passed.

        :param alarm: called once, 0.05 seconds into the run, after the first draw.
        """

        def unhandled(key: str | tuple[str, int, int, int]) -> None:
            keys.append(typing.cast("str", key))
            if len(keys) == count:
                raise urwid.ExitMainLoop

        def give_up(_loop: urwid.MainLoop, _data: object) -> typing.NoReturn:
            raise urwid.ExitMainLoop

        loop = urwid.MainLoop(urwid.SolidFill("x"), screen=screen, handle_mouse=False, unhandled_input=unhandled)
        if alarm is not None:
            loop.set_alarm_in(0.05, lambda *_args: alarm())
        loop.set_alarm_in(1, give_up)
        loop.run()
        return loop

    def test_main_loop_reads_a_key_from_the_device(self) -> None:
        """A main loop on the screen draws to the device and gets the key the device reports."""
        screen, device = self._screen()
        keys: list[str] = []
        up_pressed = packet(lcd.CFLCDScreen.CMD_KEY_ACTIVITY, bytes([1]))

        loop = self._run(screen, keys, 1, alarm=lambda: device.send(up_pressed))

        self.assertEqual(["up"], keys)
        # The run ends with "up" still held, so a repeat was pending; stopping the loop removed it with the watch.
        event_loop = typing.cast("urwid.SelectEventLoop", loop.event_loop)
        self.assertEqual({}, event_loop._watch_files)
        self.assertNotIn("read_device", [callback.__name__ for _time, _tie, callback in event_loop._alarms])
        sent = device.recv(4096)
        self.assertEqual(lcd.CFLCDScreen.CMD_LCD_DATA, sent[0])
        self.assertIn(b"x" * 20, sent)

    def test_ack_sends_the_next_queued_command(self) -> None:
        """Each command waits for the device's ACK, which the main loop reads and answers with the next one."""
        screen, device = self._screen()
        keys: list[str] = []
        ack = packet(0x40 | lcd.CFLCDScreen.CMD_LCD_DATA)
        exit_pressed = packet(lcd.CFLCDScreen.CMD_KEY_ACTIVITY, bytes([6]))

        self._run(screen, keys, 1, alarm=lambda: device.send(ack * 3 + exit_pressed))

        self.assertEqual(["esc"], keys)
        sent = device.recv(4096)
        rows = [sent[i : i + 26] for i in range(0, len(sent), 26)]
        self.assertEqual([bytes([lcd.CFLCDScreen.CMD_LCD_DATA, 22, 0, row]) for row in range(4)], [r[:4] for r in rows])

    def test_one_wake_up_reads_a_whole_packet(self) -> None:
        """A packet that arrived at once is handled by one call of the device watch, not one call per byte."""
        screen, device = self._screen()
        event_loop = urwid.SelectEventLoop()
        received: list[list[str]] = []
        screen.hook_event_loop(event_loop, lambda keys, _raw: received.append(keys))
        self.addCleanup(screen.unhook_event_loop, event_loop)
        device.send(packet(lcd.CFLCDScreen.CMD_KEY_ACTIVITY, bytes([5])))  # enter pressed

        event_loop._loop()

        self.assertEqual([["enter"]], received)

    def _hooked(self) -> tuple[lcd.CF635Screen, socket.socket, urwid.SelectEventLoop]:
        """Return a screen hooked into a select loop, its device end and the loop.

        The ACK alarm is due only after ten seconds, so only the test fires it, through :meth:`_fire_ack_alarm`,
        while a wait for input that never comes still ends.
        """
        screen, device = self._screen()
        screen.ACK_TIMEOUT = 10
        event_loop = urwid.SelectEventLoop()
        screen.hook_event_loop(event_loop, lambda _keys, _raw: None)
        self.addCleanup(screen.unhook_event_loop, event_loop)
        return screen, device, event_loop

    @staticmethod
    def _received(device: socket.socket) -> list[bytes]:
        """Return the packets the device received since the last call, each without its CRC."""
        device.setblocking(False)
        try:
            data = device.recv(4096)
        except BlockingIOError:
            data = b""
        finally:
            device.settimeout(1)
        packets = []
        while data:
            end = 2 + data[1]
            packets.append(data[:end])
            data = data[end + 2 :]
        return packets

    @staticmethod
    def _answer(device: socket.socket, event_loop: urwid.SelectEventLoop, codes: list[int]) -> None:
        """Answer one command per code with its ACK, one event loop iteration each, as a device does."""
        for code in codes:
            device.send(packet(0x40 | code))
            event_loop._loop()

    def _fire_ack_alarm(self, event_loop: urwid.SelectEventLoop) -> None:
        """Run the one pending alarm, which has to be the ACK timeout, without waiting for it."""
        self.assertEqual(1, len(event_loop._alarms))
        _time, _tie_break, callback = event_loop._alarms.pop()
        self.assertEqual("_ack_timed_out", callback.__name__)
        callback()

    def test_late_ack_sends_the_command_again(self) -> None:
        """A command whose ACK does not arrive in time is sent again, and its ACK is timed again."""
        screen, device, event_loop = self._hooked()
        backlight = bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50])
        before = time.monotonic()
        screen.set_backlight(50)
        after = time.monotonic()
        self.assertEqual([backlight], self._received(device))
        self.assertEqual(1, len(event_loop._alarms))
        self.assertLessEqual(before + screen.ACK_TIMEOUT, event_loop._alarms[0][0])
        self.assertLessEqual(event_loop._alarms[0][0], after + screen.ACK_TIMEOUT)

        self._fire_ack_alarm(event_loop)

        self.assertEqual([backlight], self._received(device))
        self.assertEqual(1, len(event_loop._alarms))

    def test_unanswered_command_is_dropped_for_the_next(self) -> None:
        """A command sent again ACK_RESENDS times without an ACK is dropped, with a warning, and the next is sent."""
        screen, device, event_loop = self._hooked()
        screen.set_backlight(50)
        screen.set_lcd_contrast(99)
        self._fire_ack_alarm(event_loop)
        for _ in range(screen.ACK_RESENDS - 1):
            self._fire_ack_alarm(event_loop)
        with self.assertLogs(screen.logger, "WARNING"):
            self._fire_ack_alarm(event_loop)

        backlight = bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50])
        contrast = bytes([lcd.CFLCDScreen.CMD_LCD_CONTRAST, 1, 99])
        self.assertEqual([backlight] * (screen.ACK_RESENDS + 1) + [contrast], self._received(device))

    def test_ack_and_error_response_send_the_next_command(self) -> None:
        """An ACK, or an error response with a warning, sends the next command, and the last ACK ends the timing."""
        backlight = bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50])
        contrast = bytes([lcd.CFLCDScreen.CMD_LCD_CONTRAST, 1, 99])
        for response, level in ((0x40, None), (0xC0, "WARNING")):
            with self.subTest(response=hex(response)):
                screen, device, event_loop = self._hooked()
                screen.set_backlight(50)
                screen.set_lcd_contrast(99)
                device.send(packet(response | lcd.CFLCDScreen.CMD_BACKLIGHT))

                with self.assertLogs(screen.logger, level) if level else self.assertNoLogs(screen.logger, "WARNING"):
                    event_loop._loop()

                self.assertEqual([backlight, contrast], self._received(device))
                device.send(packet(0x40 | lcd.CFLCDScreen.CMD_LCD_CONTRAST))
                event_loop._loop()
                self.assertEqual([], event_loop._alarms)

    def test_answer_to_a_resent_copy_does_not_release_the_next_command(self) -> None:
        """After a resend, the answer to the second copy is not taken as the answer to the next command."""
        screen, device, event_loop = self._hooked()
        rows = [bytearray([0, row, *b"row"]) for row in range(3)]
        for row in rows:
            screen.queue_command(lcd.CFLCDScreen.CMD_LCD_DATA, row)
        sent = [bytes([lcd.CFLCDScreen.CMD_LCD_DATA, 5, *row]) for row in rows]
        ack = packet(0x40 | lcd.CFLCDScreen.CMD_LCD_DATA)
        self._fire_ack_alarm(event_loop)  # row 0 is sent again
        self.assertEqual([sent[0], sent[0]], self._received(device))

        device.send(ack)  # the answer to the first copy of row 0
        event_loop._loop()
        self.assertEqual([sent[1]], self._received(device))
        device.send(ack)  # the answer to the second copy of row 0, not to row 1
        event_loop._loop()
        self.assertEqual([], self._received(device))
        device.send(ack)  # the answer to row 1
        event_loop._loop()
        self.assertEqual([sent[2]], self._received(device))

    def test_dropped_command_redraws_and_keeps_settings(self) -> None:
        """A dropped command discards the queued draw commands and makes the next draw send every row again.

        Commands that are not draws stay queued, and the device going silent and coming back is logged once each.
        """
        screen, device, event_loop = self._hooked()
        canvas = urwid.SolidFill("x").render(screen.DISPLAY_SIZE)
        screen.draw_screen(screen.DISPLAY_SIZE, canvas)
        screen.set_backlight(50)
        self._received(device)

        for _ in range(screen.ACK_RESENDS):
            self._fire_ack_alarm(event_loop)
        with self.assertLogs(screen.logger, "WARNING"):
            self._fire_ack_alarm(event_loop)
        self.assertEqual(bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50]), self._received(device)[-1])

        with self.assertNoLogs(screen.logger, "WARNING"):
            for _ in range(screen.ACK_RESENDS + 1):
                self._fire_ack_alarm(event_loop)
        self.assertEqual([], event_loop._alarms)
        self._received(device)

        screen.draw_screen(screen.DISPLAY_SIZE, canvas)
        with self.assertLogs(screen.logger, "INFO") as logs:
            self._answer(device, event_loop, [lcd.CFLCDScreen.CMD_LCD_DATA] * 4 + [lcd.CFLCDScreen.CMD_CURSOR_STYLE])
        self.assertEqual(["INFO"], [record.levelname for record in logs.records])
        self.assertEqual(
            [bytes([lcd.CFLCDScreen.CMD_LCD_DATA, 22, 0, row, *b"x" * 20]) for row in range(4)]
            + [bytes([lcd.CFLCDScreen.CMD_CURSOR_STYLE, 1, lcd.CFLCDScreen.CURSOR_NONE])],
            self._received(device),
        )

    def test_redraw_after_a_dropped_row_is_answered(self) -> None:
        """When the device answers again after a row was dropped, the answers to the redrawn rows are not ignored."""
        screen, device, event_loop = self._hooked()
        canvas = urwid.SolidFill("x").render(screen.DISPLAY_SIZE)
        screen.draw_screen(screen.DISPLAY_SIZE, canvas)
        with self.assertLogs(screen.logger, "WARNING"):
            for _ in range(screen.ACK_RESENDS + 1):
                self._fire_ack_alarm(event_loop)
        self._received(device)

        screen.draw_screen(screen.DISPLAY_SIZE, canvas)
        self._answer(device, event_loop, [lcd.CFLCDScreen.CMD_LCD_DATA] * 4)

        self.assertEqual(
            [bytes([lcd.CFLCDScreen.CMD_LCD_DATA, 22, 0, row, *b"x" * 20]) for row in range(4)]
            + [bytes([lcd.CFLCDScreen.CMD_CURSOR_STYLE, 1, lcd.CFLCDScreen.CURSOR_NONE])],
            self._received(device),
        )

    def test_lost_packet_costs_one_timeout_not_one_per_row(self) -> None:
        """An answer taken as a stray and followed by a timeout counts as the waiting row's own answer."""
        screen, device, event_loop = self._hooked()
        rows = [bytearray([0, row, *b"row"]) for row in range(4)]
        for row in rows:
            screen.queue_command(lcd.CFLCDScreen.CMD_LCD_DATA, row)
        sent = [bytes([lcd.CFLCDScreen.CMD_LCD_DATA, 5, *row]) for row in rows]
        self._fire_ack_alarm(event_loop)  # the first copy of row 0 was lost
        self._answer(device, event_loop, [lcd.CFLCDScreen.CMD_LCD_DATA] * 2)  # row 0, then row 1 taken as a stray
        self.assertEqual([sent[0], sent[0], sent[1]], self._received(device))

        screen._screen_buf = [[b"row"]]  # as drawn, to see the counted-as-answered row clear it
        self._fire_ack_alarm(event_loop)
        self.assertEqual([], screen._screen_buf)
        self._answer(device, event_loop, [lcd.CFLCDScreen.CMD_LCD_DATA])

        self.assertEqual([sent[2], sent[3]], self._received(device))

    def test_unhook_removes_the_pending_ack_alarm(self) -> None:
        """Unhooking while a command awaits its ACK leaves no alarm behind."""
        screen, _device = self._screen()
        event_loop = urwid.SelectEventLoop()
        screen.hook_event_loop(event_loop, lambda _keys, _raw: None)
        screen.set_backlight(50)

        screen.unhook_event_loop(event_loop)

        self.assertEqual([], event_loop._alarms)

    def test_refusal_is_logged_once_and_counts_as_an_answer(self) -> None:
        """A refused command is logged once per command, a refusal ends an outage like an ACK does, and no repaint."""
        screen, device, event_loop = self._hooked()
        screen.set_backlight(50)
        with self.assertLogs(screen.logger, "WARNING"):
            for _ in range(screen.ACK_RESENDS + 1):
                self._fire_ack_alarm(event_loop)
        screen.set_backlight(60)
        screen.set_backlight(70)

        screen._screen_buf = [[b"row"]]  # as drawn, to see that a refusal keeps it
        with self.assertLogs(screen.logger, "INFO") as logs:
            for _ in range(2):
                device.send(packet(0xC0 | lcd.CFLCDScreen.CMD_BACKLIGHT))
                event_loop._loop()

        self.assertEqual(["INFO", "ERROR"], [record.levelname for record in logs.records])
        self.assertEqual([[b"row"]], screen._screen_buf)
        self.assertEqual([], event_loop._alarms)

    def test_queued_rows_are_replaced_by_newer_frames(self) -> None:
        """Frames drawn while the device has not answered leave one queued command per row, with the latest text."""
        screen, device, event_loop = self._hooked()
        for text in ("a", "b", "c"):
            screen.draw_screen(screen.DISPLAY_SIZE, urwid.SolidFill(text).render(screen.DISPLAY_SIZE))
        screen.set_backlight(50)

        self._answer(
            device,
            event_loop,
            [lcd.CFLCDScreen.CMD_LCD_DATA] * 4 + [lcd.CFLCDScreen.CMD_CURSOR_STYLE, lcd.CFLCDScreen.CMD_LCD_DATA],
        )

        # Row 0 of the first frame was already sent, so the newest row 0 waits behind the queued commands.
        row = lcd.CFLCDScreen.CMD_LCD_DATA
        self.assertEqual(
            [bytes([row, 22, 0, 0, *b"a" * 20])]
            + [bytes([row, 22, 0, y, *b"c" * 20]) for y in range(1, 4)]
            + [bytes([lcd.CFLCDScreen.CMD_CURSOR_STYLE, 1, lcd.CFLCDScreen.CURSOR_NONE])]
            + [bytes([row, 22, 0, 0, *b"c" * 20])]
            + [bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50])],
            self._received(device),
        )

    def test_command_sent_before_the_hook_is_timed(self) -> None:
        """A command sent before the screen was hooked into a loop gets its ACK timed from the hook on."""
        screen, device = self._screen()
        screen.set_backlight(50)
        event_loop = urwid.SelectEventLoop()
        screen.hook_event_loop(event_loop, lambda _keys, _raw: None)
        self.addCleanup(screen.unhook_event_loop, event_loop)

        self._fire_ack_alarm(event_loop)

        self.assertEqual([bytes([lcd.CFLCDScreen.CMD_BACKLIGHT, 1, 50])] * 2, self._received(device))

    def test_held_key_repeats(self) -> None:
        """A key held down on the device is repeated after the repeat delay, with no further data from it."""
        screen, device = self._screen(repeat_delay=0.05, repeat_next=0.05)
        keys: list[str] = []
        device.send(packet(lcd.CFLCDScreen.CMD_KEY_ACTIVITY, bytes([3])))  # left pressed, never released

        self._run(screen, keys, 3)

        self.assertEqual(["left", "left", "left"], keys)
