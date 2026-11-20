# Urwid escape sequences common to curses_display and raw_display
#    Copyright (C) 2004-2011  Ian Ward
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


"""Decoding of a queue of input codes into key and mouse event names."""

from __future__ import annotations

import contextlib
import sys
import typing

from urwid import str_util, util
from urwid.display.escape._keys import input_sequences
from urwid.display.escape._sequences import _C1_CONTROLS
from urwid.display.escape._trie import _CSI_PARAMETERS_MAX_LEN, KeyqueueTrie, MoreInputRequired

if typing.TYPE_CHECKING:
    from urwid.display.escape._trie import (
        _CursorPosition,
        _KeyboardProtocol,
        _MouseInput,
        _TerminalReport,
    )


IS_WINDOWS: typing.Final = sys.platform == "win32"


#################################################
# Build the input trie from input_sequences list
input_trie = KeyqueueTrie(input_sequences)
#################################################

_keyconv = {
    8: "backspace",
    9: "tab",
    10: "enter",
    13: "enter",
    127: "backspace",
    # curses-only keycodes follow..  (XXX: are these used anymore?)
    258: "down",
    259: "up",
    260: "left",
    261: "right",
    262: "home",
    263: "backspace",
    265: "f1",
    266: "f2",
    267: "f3",
    268: "f4",
    269: "f5",
    270: "f6",
    271: "f7",
    272: "f8",
    273: "f9",
    274: "f10",
    275: "f11",
    276: "f12",
    277: "shift f1",
    278: "shift f2",
    279: "shift f3",
    280: "shift f4",
    281: "shift f5",
    282: "shift f6",
    283: "shift f7",
    284: "shift f8",
    285: "shift f9",
    286: "shift f10",
    287: "shift f11",
    288: "shift f12",
    330: "delete",
    331: "insert",
    338: "page down",
    339: "page up",
    343: "enter",  # on numpad
    350: "5",  # on numpad
    360: "end",
}


if IS_WINDOWS:
    _keyconv[351] = "shift tab"
    _keyconv[358] = "end"


def _control_sequence_length(codes: list[int], more_available: bool, *, start: int = 0) -> int | None:
    """Return the length of the ECMA-48 control sequence body at the start of ``codes[start:]``.

    :param codes: the codes following ``ESC [`` from *start* on.
    :param more_available: if True then raise MoreInputRequired when the codes end before the final byte.
    :param start: the position in *codes* where the body starts.
    :returns: the number of codes up to and including the final byte, or None when the codes do not start with
        at least one parameter or intermediate byte and a final byte, in that order,
        within ``_CSI_PARAMETERS_MAX_LEN`` bytes before the final byte.
        A final byte straight after ``ESC [`` is not taken, so that :kbd:`Alt+[` followed by a key stays two keys.
    :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
    """
    intermediate = False
    for pos, code in enumerate(codes[start : start + _CSI_PARAMETERS_MAX_LEN + 1]):
        if 0x40 <= code <= 0x7E:
            return pos + 1 if pos else None
        if 0x20 <= code <= 0x2F:
            intermediate = True
        elif intermediate or not 0x30 <= code <= 0x3F:
            return None
    if more_available and len(codes) - start <= _CSI_PARAMETERS_MAX_LEN:
        raise MoreInputRequired
    return None


def process_keyqueue(
    codes: list[int],
    more_available: bool,
    *,
    keyboard_protocol: _KeyboardProtocol | None = None,
) -> tuple[list[str | _MouseInput | _CursorPosition | _TerminalReport], list[int]]:
    """Decode `codes` into input events, consuming as much of the queue as is currently decodable.

    Each call copies the codes it leaves, so a loop calling it until the codes run out takes time quadratic in their
    number; :func:`decode_input` decodes them all in linear time.

    :param codes: list of key codes
    :param more_available: if True then raise MoreInputRequired when in the middle of a character sequence
        (escape/utf8/wide) and caller will attempt to send more key codes on the next call.
    :param keyboard_protocol: the keyboard protocol the terminal has on. With the kitty keyboard protocol, CSI P is F1
        rather than the Delete key st sends it for; with xterm's modifyOtherKeys, a CSI u report carries the character
        typed with shift.
    :returns: a ``(list of input, list of remaining key codes)`` tuple.
        The list of input is empty when the codes consumed are a mouse report cut short.
    :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
    """
    run, end = _process_keyqueue_at(codes, 0, more_available, keyboard_protocol=keyboard_protocol)
    return run, codes[end:]


def decode_input(
    codes: list[int],
    more_available: bool,
    *,
    keyboard_protocol: _KeyboardProtocol | None = None,
) -> tuple[list[str | _MouseInput | _CursorPosition | _TerminalReport], int]:
    """Decode every input event in *codes*.

    The time taken is linear in the number of codes.

    >>> decode_input([ord("a"), 27, ord("["), ord("B"), 27, ord("[")], more_available=True)
    (['a', 'down'], 4)
    >>> decode_input([ord("a"), 27, ord("["), ord("B"), 27, ord("[")], more_available=False)
    (['a', 'down', 'meta ['], 6)

    :param codes: list of key codes
    :param more_available: if True then stop at a sequence the codes end in the middle of,
        since the caller will pass it again together with the codes that follow.
        If False then decode such a sequence as well as it can be decoded.
    :param keyboard_protocol: see :func:`process_keyqueue`.
    :returns: the decoded input and the number of codes it was decoded from.
        The codes from that number on are the start of an incomplete sequence, which only *more_available* leaves.
    """
    decoded: list[str | _MouseInput | _CursorPosition | _TerminalReport] = []
    pos = 0
    with contextlib.suppress(MoreInputRequired):
        while pos < len(codes):
            run, pos = _process_keyqueue_at(codes, pos, more_available, keyboard_protocol=keyboard_protocol)
            decoded.extend(run)
    return decoded, pos


def _process_keyqueue_at(
    codes: list[int],
    start: int,
    more_available: bool,
    *,
    keyboard_protocol: _KeyboardProtocol | None,
) -> tuple[list[str | _MouseInput | _CursorPosition | _TerminalReport], int]:
    """Do what :func:`process_keyqueue` does for ``codes[start:]``, returning the position after the input.

    :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
    """
    code = codes[start]
    if 32 <= code <= 126:
        key = chr(code)
        return [key], start + 1
    if code in _keyconv:
        return [_keyconv[code]], start + 1
    if 0 < code < 27:
        return [f"ctrl {ord('a') + code - 1:c}"], start + 1
    if 27 < code < 32:
        return [f"ctrl {ord('A') + code - 1:c}"], start + 1

    em = str_util.get_byte_encoding()

    if em == "utf8" and 127 < code < 256:
        if code & 0xE0 == 0xC0:  # 2-byte form
            need_more = 1
        elif code & 0xF0 == 0xE0:  # 3-byte form
            need_more = 2
        elif code & 0xF8 == 0xF0:  # 4-byte form
            need_more = 3
        else:
            return [f"<{code:d}>"], start + 1

        for i in range(1, need_more + 1):
            if len(codes) - start <= i:
                if more_available:
                    raise MoreInputRequired

                return [f"<{code:d}>"], start + 1

            k = codes[start + i]
            if k > 256 or k & 0xC0 != 0x80:
                return [f"<{code:d}>"], start + 1

        s = bytes(codes[start : start + need_more + 1])

        try:
            key = s.decode("utf-8")
        except UnicodeDecodeError:
            return [f"<{code:d}>"], start + 1
        # a C1 control is named by its value, as a byte that is not valid UTF-8 is, so it is not received as text
        return [f"<{ord(key):d}>" if ord(key) in _C1_CONTROLS else key], start + need_more + 1

    if (
        em == "wide"
        and code < 256
        and str_util.within_double_byte(
            (start_code := code.to_bytes(1, "little")),
            0,
            0,
        )
    ):
        if start + 1 == len(codes) and more_available:
            raise MoreInputRequired
        if start + 1 < len(codes) and codes[start + 1] < 256:
            end_code = codes[start + 1].to_bytes(1, "little")

            if str_util.within_double_byte(start_code + end_code, 0, 1):
                # a pair that is not a character of the encoding falls through and is decoded byte by byte
                with contextlib.suppress(UnicodeDecodeError):
                    return [(start_code + end_code).decode(util.get_encoding())], start + 2

    if 127 < code < 256:
        try:
            key = code.to_bytes(1, "little").decode(util.get_encoding())
        except UnicodeDecodeError:
            key = chr(code)  # not a character of the encoding (always for "ascii"): read the byte as Latin-1
        # a C1 control, such as byte 0x9B in ISO-8859-1, is named by its value as in UTF-8
        return [f"<{code:d}>" if ord(key) in _C1_CONTROLS else key], start + 1
    if code != 27:
        return [f"<{code:d}>"], start + 1

    if keyboard_protocol == "kitty" and codes[start + 1 : start + 3] == [ord("["), ord("P")]:
        return ["f1"], start + 3

    shift_applied = keyboard_protocol == "modify other keys"
    # pylint: disable-next=protected-access  # the offset form of KeyqueueTrie.get, private to this module
    if (result := input_trie._get_at(codes, start + 1, more_available, csi_u_shift_applied=shift_applied)) is not None:
        decoded, end = result
        return ([] if decoded is None else [decoded]), end

    # An unrecognised control sequence is one key: decoding it byte by byte would type its body as text.
    if (
        codes[start + 1 : start + 2] == [ord("[")]
        and (length := _control_sequence_length(codes, more_available, start=start + 2)) is not None
    ):
        return [f"<csi {bytes(codes[start + 2 : start + 2 + length]).decode('ascii')}>"], start + 2 + length

    if codes[start + 1 : start + 3] == [27, 27]:
        # With a third ESC following, the second one cannot start a sequence the first one prefixes as meta,
        # so decode the first one alone rather than recursing once per ESC in an arbitrarily long run.
        return ["esc"], start + 1

    if len(codes) - start > 1:
        # Meta keys -- ESC+Key form
        run, end = _process_keyqueue_at(codes, start + 1, more_available, keyboard_protocol=keyboard_protocol)
        # A mouse event or a terminal report (cursor position, DECRPM, a query reply) cannot take a meta prefix,
        # and an unrecognised control sequence may be such a report.
        if not run or not isinstance(run[0], str) or run[0] == "esc" or "meta " in run[0] or run[0].startswith("<csi "):
            return ["esc", *run], end
        return [f"meta {run[0]}", *run[1:]], end

    return ["esc"], start + 1
