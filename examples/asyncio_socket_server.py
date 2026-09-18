#!/usr/bin/env python
"""Demo of using urwid with Python asyncio."""

from __future__ import annotations

import asyncio
import logging
import sys
import typing
import weakref
from datetime import datetime

import urwid
from urwid.display.raw import Screen

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    # Mirrors the private urwid.display._raw_display_base.Screen._DecodedInput alias, which isn't exported.
    _DecodedInput = list[str | tuple[str, int, int, int] | tuple[typing.Literal["cursor position"], int, int]]

logging.basicConfig()

loop = asyncio.get_event_loop()


# -----------------------------------------------------------------------------
# General-purpose setup code


def build_widgets() -> urwid.Filler[urwid.Pile]:
    """Build the demo widget tree, with a self-updating clock and three text inputs.

    :returns: the top-level widget for the demo.
    """
    input1 = urwid.Edit("What is your name? ")
    input2 = urwid.Edit("What is your quest? ")
    input3 = urwid.Edit("What is the capital of Assyria? ")
    inputs = [input1, input2, input3]

    def update_clock(widget_ref: weakref.ReferenceType[urwid.Text]) -> None:
        widget = widget_ref()
        if not widget:
            # widget is dead; the main loop must've been destroyed
            return

        widget.set_text(datetime.now().isoformat())  # noqa: DTZ005  # use naive time

        # Schedule us to update the clock again in one second
        loop.call_later(1, update_clock, widget_ref)

    clock = urwid.Text("")
    update_clock(weakref.ref(clock))

    return urwid.Filler(urwid.Pile([clock, *inputs]), urwid.TOP)


def unhandled(key: str | tuple[str, int, int, int]) -> None:
    """Exit the main loop when the user presses :kbd:`ctrl c`.

    :param key: the unhandled key or mouse event passed by :class:`urwid.MainLoop`.
    :raises urwid.ExitMainLoop: always, when ``key`` is :kbd:`ctrl c`.
    """
    if key == "ctrl c":
        raise urwid.ExitMainLoop


# -----------------------------------------------------------------------------
# Demo 1


def demo1() -> None:
    """Plain old urwid app.  Just happens to be run atop asyncio as the event
    loop.

    Note that the clock is updated using the asyncio loop directly, not via any
    of urwid's facilities.
    """
    main_widget = build_widgets()

    urwid_loop = urwid.MainLoop(
        main_widget,
        event_loop=urwid.AsyncioEventLoop(loop=loop),
        unhandled_input=unhandled,
    )
    urwid_loop.run()


# -----------------------------------------------------------------------------
# Demo 2


class AsyncScreen(Screen):
    """An urwid screen that speaks to an asyncio stream, rather than polling
    file descriptors.

    This is fairly limited; it can't, for example, determine the size of the
    remote screen.  Fixing that depends on the nature of the stream.
    """

    _pending_task: asyncio.Task[bytes] | None

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.WriteTransport, encoding: str = "utf-8") -> None:
        self.reader = reader
        self.writer = writer
        self.encoding = encoding

        # AsyncScreen overrides every method that would touch the underlying input/output files, so the defaults
        # (sys.stdin/sys.stdout) used by the base Screen are never actually read from or written to.
        super().__init__()

    def write(self, data: str) -> None:
        self.writer.write(data.encode(self.encoding))

    def flush(self) -> None:
        pass

    def hook_event_loop(
        self,
        event_loop: urwid.EventLoop,
        callback: Callable[[_DecodedInput, list[int]], typing.Any],
    ) -> None:
        """Pump input from the asyncio stream reader into the urwid event loop.

        :param event_loop: must be an :class:`urwid.AsyncioEventLoop`, since it needs asyncio's ``create_task``.
        :raises TypeError: if ``event_loop`` is not an :class:`urwid.AsyncioEventLoop`.
        """
        if not isinstance(event_loop, urwid.AsyncioEventLoop):
            msg = "AsyncScreen requires an AsyncioEventLoop"
            raise TypeError(msg)

        # Wait on the reader's read coro, and when there's data to read, call
        # the callback and then wait again
        def pump_reader(fut: asyncio.Future[bytes] | None = None) -> None:
            if fut is None:
                # First call, do nothing
                pass
            elif fut.cancelled():
                # This is in response to an earlier .read() call, so don't
                # schedule another one!
                return
            elif fut.exception():
                pass
            else:
                try:
                    self.parse_input(event_loop, callback, list(fut.result()))
                except urwid.ExitMainLoop:
                    # This will immediately close the transport and thus the
                    # connection, which in turn calls connection_lost, which
                    # stops the screen and the loop
                    self.writer.abort()

            # create_task() schedules a coroutine without using `yield from` or
            # `await`, which are syntax errors in Pythons before 3.5
            self._pending_task = event_loop._loop.create_task(self.reader.read(1024))
            self._pending_task.add_done_callback(pump_reader)

        pump_reader()

    def unhook_event_loop(self, event_loop: urwid.EventLoop) -> None:
        if self._pending_task:
            self._pending_task.cancel()
            self._pending_task = None


class UrwidProtocol(asyncio.Protocol):
    """An asyncio protocol that drives an urwid UI over the connection."""

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Start the urwid UI once a client connects.

        :param transport: the transport for the new connection; must support writing, since :class:`AsyncScreen`
            writes urwid's output straight back to it.
        :raises TypeError: if ``transport`` doesn't support writing.
        """
        if not isinstance(transport, asyncio.WriteTransport):
            msg = "UrwidProtocol requires a write-capable transport"
            raise TypeError(msg)

        print("Got a client!")
        self.transport = transport

        # StreamReader is super convenient here; it has a regular method on our
        # end (feed_data), and a coroutine on the other end that will
        # faux-block until there's data to be read.  We could also just call a
        # method directly on the screen, but this keeps the screen somewhat
        # separate from the protocol.
        self.reader = asyncio.StreamReader(loop=loop)
        screen = AsyncScreen(self.reader, transport)

        main_widget = build_widgets()
        self.urwid_loop = urwid.MainLoop(
            main_widget,
            event_loop=urwid.AsyncioEventLoop(loop=loop),
            screen=screen,
            unhandled_input=unhandled,
        )

        self.urwid_loop.start()

    def data_received(self, data: bytes) -> None:
        """Feed received bytes to the stream reader driving :class:`AsyncScreen`."""
        self.reader.feed_data(data)

    def connection_lost(self, exc: Exception | None) -> None:
        """Tear down the urwid UI once the client disconnects."""
        print("Lost a client...")
        self.reader.feed_eof()
        self.urwid_loop.stop()


def demo2() -> None:
    """Urwid app served over the network to multiple clients at once, using an
    asyncio Protocol.
    """
    coro = loop.create_server(UrwidProtocol, port=12345)
    loop.run_until_complete(coro)
    print("OK, good to go!  Try this in another terminal (or two):")
    print()
    print("    socat TCP:127.0.0.1:12345 STDIN,rawer")
    print()
    loop.run_forever()


if __name__ == "__main__":
    if len(sys.argv) == 2:
        which: str | None = sys.argv[1]
    else:
        which = None

    if which == "1":
        demo1()
    elif which == "2":
        demo2()
    else:
        print("Please run me with an argument of either 1 or 2.")
        sys.exit(1)
