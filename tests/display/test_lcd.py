from __future__ import annotations

import socket
import typing
import unittest
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
        with mock.patch.object(serial, "Serial") as serial_cls:
            serial_cls.return_value.fileno.return_value = 7
            screen = lcd.CF635Screen("/dev/ttyUSB0")

        self.assertEqual([7], screen.get_input_descriptors())

    def _screen(self, **kwargs: typing.Any) -> tuple[lcd.CF635Screen, socket.socket]:
        """Return a screen on a fake serial port, and the device's end of that port."""
        port, device = socket.socketpair()
        self.addCleanup(port.close)
        self.addCleanup(device.close)
        device.settimeout(1)  # a test reading what was never sent fails instead of waiting
        with mock.patch.object(serial, "Serial", return_value=SocketSerial(port)):
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

    def test_held_key_repeats(self) -> None:
        """A key held down on the device is repeated after the repeat delay, with no further data from it."""
        screen, device = self._screen(repeat_delay=0.05, repeat_next=0.05)
        keys: list[str] = []
        device.send(packet(lcd.CFLCDScreen.CMD_KEY_ACTIVITY, bytes([3])))  # left pressed, never released

        self._run(screen, keys, 3)

        self.assertEqual(["left", "left", "left"], keys)
