# Urwid raw display module
#    Copyright (C) 2004-2009  Ian Ward
#
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


"""Input reading and decoding of the raw display :class:`Screen`."""

from __future__ import annotations

import abc
import functools
import logging
import selectors
import time
import typing

from urwid import _deprecation
from urwid._selectors import read_selector
from urwid.display import escape
from urwid.display._raw_display_base._modes import _ModesScreen

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import Literal

    from urwid import EventLoop
    from urwid.display._raw_display_base._base import SupportsFileno
    from urwid.display._raw_display_base._modes import _DecodedInput


# most input passes a resize waits for the input typed before it, so input that keeps coming cannot hold it forever
_RESIZE_HOLD_PASSES = 64


class _InputScreen(_ModesScreen):
    """Read the input of a raw display :class:`Screen` and decode it into keys, mouse events and reports."""

    __slots__ = ()

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> _DecodedInput: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[_DecodedInput, list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> _DecodedInput | tuple[_DecodedInput, list[int]]:
        r"""Return pending input as a list.

        :param raw_keys: return raw keycodes as well as translated versions
        :raises RuntimeError: the screen has not been started.
        :raises InputClosedError: the input reached end of file.

        This function will immediately return all the input since the
        last time it was called.  If there is no input pending it will
        wait before returning an empty list.  The wait time may be
        configured with the set_input_timeouts function.

        A key that can begin a longer sequence, such as Esc, is kept until the rest of the sequence arrives
        or *complete_wait* is over, so the list can be empty before *max_wait* is over.

        If raw_keys is False (default) this function will return a list
        of keys pressed.  If raw_keys is True this function will return
        a ( keys pressed, raw keycodes ) tuple instead.

        Examples of keys returned:

        * ASCII printable characters:  :kbd:`space`, :kbd:`a`, :kbd:`0`, :kbd:`A`, :kbd:`-`, :kbd:`/`
        * ASCII control characters:  :kbd:`tab`, :kbd:`enter`
        * Escape sequences:  :kbd:`up`, :kbd:`page up`, :kbd:`home`, :kbd:`insert`, :kbd:`f1`
        * Key combinations:  :kbd:`shift f1`, :kbd:`meta a`, :kbd:`ctrl b`
        * Window events:  ``"window resize"``

        Other characters, decoded from the terminal encoding (UTF-8, or a single- or double-byte encoding):

        * Unicode characters: "\u00a5", "\u253c", "\u4e2d"

        Examples of mouse events returned:

        * Mouse button press: ('mouse press', 1, 15, 13),
                              ('meta mouse press', 2, 17, 23)
        * Mouse drag: ('mouse drag', 1, 16, 13),
                      ('mouse drag', 1, 17, 13),
                      ('ctrl mouse drag', 1, 18, 13)
        * Mouse button release: ('mouse release', 0, 18, 13),
                                ('ctrl mouse release', 0, 17, 23)

        The button number is a :class:`~urwid.MouseButton` value.
        """
        logger = self.logger.getChild("get_input")
        if not self._started:
            raise RuntimeError

        now = time.monotonic()
        # counted with the complete_wait in effect now, which set_input_timeouts() may have changed since the read
        partial_deadline = self._partial_read_time + self.complete_wait
        # The waits for more input after a resize end by the time max_wait would have ended.
        deadline = None if self.max_wait is None else now + self.max_wait
        partial: list[int] = self._partial_codes
        keys: _DecodedInput = []
        raw: list[int] = []
        wait = self.max_wait
        if partial and now >= partial_deadline:
            # Its deadline passed before this call: it is decoded alone, ahead of the input that came since.
            # A pending resize is left to the parse after the read, which knows whether input came before it.
            self._partial_codes = []
            keys, _consumed = self._decode_codes(partial, wait_for_more=False)
            raw = partial
            partial = []
            wait = 0.0
        elif partial:
            # the rest of a sequence cut short is waited for only until its deadline
            left = max(0.0, partial_deadline - now)
            wait = left if wait is None else min(wait, left)
        self._wait_for_input_ready(wait)
        codes = self.get_available_raw_input()
        read_new = len(codes) > len(partial)
        # a sequence cut short, with no more of it by its deadline, is decoded as it is
        expired = bool(partial) and not read_new and time.monotonic() >= partial_deadline
        new_keys, new_raw = self.parse_input(None, None, codes, wait_for_more=not expired)
        keys = [*keys, *new_keys]
        raw = [*raw, *new_raw]

        # Avoid pegging CPU at 100% when slowly resizing; not while a sequence cut short waits for its rest
        if keys == ["window resize"] and self.prev_input_resize and not self._partial_codes:
            logger.debug('get_input: got "window resize" > 1 times. Enable throttling for resize.')
            for _ in range(2):
                wait = self.resize_wait
                if deadline is not None:
                    wait = min(wait, max(0.0, deadline - time.monotonic()))
                self._wait_for_input_ready(wait)
                new_codes = self.get_available_raw_input()
                read_new = read_new or bool(new_codes)
                new_keys, new_raw = self.parse_input(None, None, new_codes)
                raw += new_raw
                if new_keys and new_keys != ["window resize"]:
                    if "window resize" in new_keys:
                        keys = new_keys
                    else:
                        keys.extend(new_keys)
                    break

        if keys == ["window resize"]:
            self.prev_input_resize = 2
        elif self.prev_input_resize == 2 and not keys:
            self.prev_input_resize = 1
        else:
            self.prev_input_resize = 0

        # each read that leaves a sequence cut short gives it complete_wait to arrive whole
        if self._partial_codes and read_new:
            self._partial_read_time = time.monotonic()

        if raw_keys:
            return keys, raw
        return keys

    def get_input_descriptors(self) -> list[SupportsFileno | int]:
        """Return a list of integer file descriptors that should be polled in external event loops.

        Used to check for user input. Use this method if you are implementing your own event loop.

        This method is only called by `hook_event_loop`, so if you override
        that, you can safely ignore this.
        """
        if not self._started:
            return []

        fd_list: list[SupportsFileno | int] = [self._resize_pipe_rd]

        if (input_io := self._term_input_io) is not None:
            fd_list.append(input_io)
        return fd_list

    _current_event_loop_handles: Sequence[typing.Any] = ()

    @abc.abstractmethod
    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """Remove any hooks added by hook_event_loop."""

    @abc.abstractmethod
    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[_DecodedInput, list[int]], typing.Any],
    ) -> None:
        """Register the given callback with the event loop, to be called with new input whenever it's available.

        The callback should be passed a list of processed keys and a list of unprocessed keycodes.

        Subclasses may wish to use parse_input to wrap the callback.

        .. deprecated:: 5.0
            A subclass that defines ``get_input_nonblocking()`` is still polled through it.
            Override :meth:`get_available_raw_input` instead. This API will be removed in version 7.0.
        """

    _input_timeout: typing.Any = None

    def _make_legacy_input_wrapper(
        self,
        event_loop: EventLoop,
        callback: Callable[[_DecodedInput, list[int]], typing.Any],
    ) -> Callable[[], None]:
        """Support old Screen classes that still have a get_input_nonblocking and expect it to work.

        :warns DeprecationWarning: always, since overriding ``get_input_nonblocking()`` is deprecated.
        """
        _deprecation.warn(
            f"{self.__class__.__module__}.{self.__class__.__qualname__} defines get_input_nonblocking(). "
            "Override get_available_raw_input() instead.",
            since="5.0",
            removed_in="7.0",
        )

        @functools.wraps(callback)
        def wrapper() -> None:
            if self._input_timeout:
                event_loop.remove_alarm(self._input_timeout)
                self._input_timeout = None

            timeout, keys, raw = self.get_input_nonblocking()  # type: ignore[attr-defined]  # pylint: disable=no-member
            if timeout is not None:
                self._input_timeout = event_loop.alarm(timeout, wrapper)

            callback(keys, raw)

        return wrapper

    def _get_input_codes(self) -> list[int]:
        return list(self._get_keyboard_codes())

    def get_available_raw_input(self) -> list[int]:
        """
        Return any currently available input. Does not block.

        This method is only used by the default `hook_event_loop`
        implementation; you can safely ignore it if you implement your own.

        :raises InputClosedError: the input reached end of file.
        """
        logger = self.logger.getChild("get_available_raw_input")
        codes = [*self._partial_codes, *self._get_input_codes()]
        self._partial_codes = []

        # clean out the pipe used to signal external event loops
        # that a resize has occurred
        with selectors.DefaultSelector() as selector:
            selector.register(self._resize_pipe_rd, selectors.EVENT_READ)
            present_resize_flag = selector.select(0)  # nonblocking
            while present_resize_flag:
                logger.debug("Resize signal received. Cleaning socket.")
                # Argument "size" is maximum buffer size to read. Since we're emptying, set it reasonably big.
                self._resize_pipe_rd.recv(128)
                present_resize_flag = selector.select(0)

        return codes

    @typing.overload
    def parse_input(
        self,
        event_loop: EventLoop | None,
        callback: None,
        codes: list[int],
        wait_for_more: bool = ...,
    ) -> tuple[_DecodedInput, list[int]]: ...

    @typing.overload
    def parse_input(
        self,
        event_loop: EventLoop | None,
        callback: Callable[[_DecodedInput, list[int]], typing.Any],
        codes: list[int],
        wait_for_more: bool = ...,
    ) -> None: ...

    def parse_input(
        self,
        event_loop: EventLoop | None,
        callback: Callable[[_DecodedInput, list[int]], typing.Any] | None,
        codes: list[int],
        wait_for_more: bool = True,
    ) -> tuple[_DecodedInput, list[int]] | None:
        """
        Read any available input from get_available_raw_input, parses it into keys, and calls the given callback.

        The current implementation tries to avoid any assumptions about what
        the screen or event loop look like; it only deals with parsing keycodes
        and setting a timeout when an incomplete one is detected.

        A terminal resize is reported as ``"window resize"`` after the input typed before it.
        When the last read of this screen's own input can have left such input waiting,
        the resize is held for a later call and the input loop is woken to read it.

        `codes` is a list of keycodes: the integer values of the input bytes, or curses key codes.
        """
        logger = self.logger.getChild("parse_input")

        # Note: event_loop may be None for 100% synchronous support, only used
        # by get_input.  Not documented because you shouldn't be doing it.
        if self._input_timeout and event_loop:
            event_loop.remove_alarm(self._input_timeout)
            self._input_timeout = None

        output_codes, consumed = self._decode_codes(codes, wait_for_more=wait_for_more)
        raw_codes = codes[:consumed]
        partial_codes = self._partial_codes = codes[consumed:]
        if partial_codes:
            # Set a timer to wait for the rest of the input; if it goes off
            # without any new input having come in, use the partial input
            def _parse_incomplete_input() -> None:
                self._input_timeout = None
                self._partial_codes = []
                self.parse_input(event_loop, callback, partial_codes, wait_for_more=False)

            if event_loop:
                self._input_timeout = event_loop.alarm(self.complete_wait, _parse_incomplete_input)

        # formats the whole input burst, so it is skipped unless the record is emitted
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Decoded codes: {output_codes!r}, raw codes: {raw_codes!r}")

        # read once: a resize recorded between two reads would skip the hold below
        resized = self._resized
        if resized and self._hold_resize and self._resize_held_passes < _RESIZE_HOLD_PASSES:
            # Input typed before the resize can still wait: report the resize after it, in a pass this wake-up starts.
            self._resize_held_passes += 1
            self._wake_input_loop()
        elif resized:
            self._resize_held_passes = 0
            self._resized = False
            # The system's size is the newer one now: a terminal without mode 2048, such as one a multiplexer session
            # was attached to, reports its size this way only.
            self._reported_cols_rows = None
            self.screen_buf = None
            if output_codes[-1:] != ["window resize"]:
                output_codes.append("window resize")
            logger.debug('Added "window resize" to the codes')

        if callback:
            callback(output_codes, raw_codes)
            return None

        # For get_input
        return output_codes, raw_codes

    def _decode_codes(self, codes: list[int], *, wait_for_more: bool) -> tuple[_DecodedInput, int]:
        """Decode *codes* into keys with the terminal reports applied.

        A pending resize is left to the caller.

        :returns: the keys, and the number of codes they were decoded from.
        """
        decoded, consumed = escape.decode_input(codes, wait_for_more, keyboard_protocol=self._keyboard_protocol_enabled)
        reported = self._apply_window_size_reports(self._apply_terminal_reports(decoded))
        return self._drop_past_end_mouse_events(reported), consumed

    def _wait_for_input_ready(self, timeout: float | None) -> list[int]:
        logger = self.logger.getChild("wait_for_input_ready")
        fd_list = self.get_input_descriptors()

        logger.debug(f"Waiting for input: descriptors={fd_list!r}, timeout={timeout!r}")
        with read_selector((fd, None) for fd in fd_list) as selector:
            ready = selector.select(timeout)

        logger.debug(f"Input ready: {ready}")

        return [event.fd for event, _ in ready]

    @abc.abstractmethod
    def _read_raw_input(self, timeout: float) -> Iterable[int]: ...

    def _get_keyboard_codes(self) -> Iterable[int]:
        return self._read_raw_input(0)
