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


"""Input trie that decodes key presses, mouse events and terminal replies from input bytes."""

from __future__ import annotations

import types
import typing
from collections.abc import MutableMapping

from urwid.display.escape._keys import (
    _CSI_LETTER_KEYS,
    _CSI_TILDE_KEYS,
    _CSI_U_KEYS,
    _MODIFY_OTHER_KEYS_NUMBER,
    _modified_key_name,
    _text_key_name,
)
from urwid.display.escape._mouse import (
    _MOUSE_BYTE_MAX,
    _MOUSE_BYTE_OFFSET,
    _MOUSE_COORD_OFFSET,
    _MOUSE_MODIFIER_PREFIXES,
    _NEXT_MOUSE_REPORT,
    _SGR_MOUSE_MAX_LEN,
    MOUSE_MULTIPLE_CLICK_MASK,
    MOUSE_RELEASE_FLAG,
    MouseBit,
    _mouse_button,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    _KeyQueueData = dict[int, "str | _KeyQueueData"]
    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _PrivateModeReport = tuple[typing.Literal["private mode report"], str, int]
    # the kitty keyboard protocol flags the terminal has in effect
    _KeyboardProtocolReport = tuple[typing.Literal["keyboard protocol report"], int]
    # an xterm key modifier resource and its value, None when the terminal reports it at its initial value
    _ModifyKeysReport = tuple[typing.Literal["modify keys report"], int, int | None]
    # the parameters of a Primary Device Attributes reply
    _DeviceAttributesReport = tuple[typing.Literal["device attributes"], tuple[int, ...]]
    # the text area size in columns and rows, from an in-band resize notification (mode 2048)
    _WindowSizeReport = tuple[typing.Literal["window size report"], int, int]
    # the terminal's name and version, as its XTVERSION reply gives them
    _TerminalVersionReport = tuple[typing.Literal["terminal version"], str]
    # the capabilities of an XTGETTCAP reply by name: their value, "" for a boolean one, None for one the terminal lacks
    _TerminalCapabilitiesReport = tuple[typing.Literal["terminal capabilities"], tuple[tuple[str, str | None], ...]]
    # the number of a dynamic color, 10 for the default foreground and 11 for the background, and its color as the
    # terminal described it in its reply to OSC 10 or OSC 11, an X11 color spec such as rgb:rrrr/gggg/bbbb
    _DefaultColorReport = tuple[typing.Literal["default color"], int, str]
    # a DECRPSS reply: whether the terminal took the request as valid, and the setting it reported
    _SettingReport = tuple[typing.Literal["setting report"], bool, str]
    _TerminalReport = (
        _PrivateModeReport
        | _KeyboardProtocolReport
        | _ModifyKeysReport
        | _DeviceAttributesReport
        | _WindowSizeReport
        | _TerminalVersionReport
        | _TerminalCapabilitiesReport
        | _DefaultColorReport
        | _SettingReport
    )
    # the keyboard protocol the terminal has on, beyond the legacy key encoding
    _KeyboardProtocol = typing.Literal["kitty", "modify other keys"]


# the most common ord() calls used for numeric decode, pre-calculate once
_ORD_0: typing.Final = ord("0")
_ORD_9: typing.Final = ord("9")


# longest body of a control sequence accepted before its final byte:
# the parameters of a key report or a terminal reply, or the parameter and intermediate bytes of an unrecognised one
_CSI_PARAMETERS_MAX_LEN: typing.Final = 64
# an in-band resize notification carries the rows and columns, optionally followed by the height and width in pixels
_WINDOW_SIZE_REPORT_LENGTHS: typing.Final = frozenset({2, 4})
# the largest row or column count a notification may carry: the range of TIOCGWINSZ's unsigned short fields
_WINDOW_SIZE_MAX: typing.Final = 0xFFFF
# the codes after ESC that start the DCS replies urwid reads: XTVERSION's, and XTGETTCAP's valid and invalid ones
_XTVERSION_INTRODUCER: typing.Final = b"P>|"
_XTGETTCAP_VALID_INTRODUCER: typing.Final = b"P1+r"
_XTGETTCAP_INTRODUCERS: typing.Final = (_XTGETTCAP_VALID_INTRODUCER, b"P0+r")
# the codes after ESC that start a DECRPSS reply, by whether the terminal took the request as valid
_DECRPSS_INTRODUCERS: typing.Final = types.MappingProxyType({b"P1$r": True, b"P0$r": False})
# the codes after ESC that start the OSC replies urwid reads, by the dynamic color they describe: OSC 10 and OSC 11
_DEFAULT_COLOR_INTRODUCERS: typing.Final = types.MappingProxyType({b"]10;": 10, b"]11;": 11})
# the starts of the color in an OSC 10 or OSC 11 reply: terminals answer in these X11 forms, rxvt-unicode with alpha
# in the second, and a body that starts otherwise is typed keys, as Alt+] followed by text
_DEFAULT_COLOR_PREFIXES: typing.Final = ("rgb:", "rgba:")
_BEL: typing.Final = 0x07
# longest body of a DCS reply accepted before its ST
_STRING_REPORT_MAX_LEN: typing.Final = 256
_HEX_DIGITS: typing.Final = frozenset("0123456789abcdefABCDEF")

###################
# Input sequences
###################


class MoreInputRequired(Exception):
    """Raised when the input decoded so far is a prefix of a longer escape sequence."""


class KeyqueueTrie:
    """Trie mapping terminal escape sequences to the key names they decode to."""

    __slots__ = ("data",)

    def __init__(self, sequences: Iterable[tuple[str, str]]) -> None:
        """
        Build a trie of the given ``(escape sequence, key name)`` pairs.

        :raises TypeError: two sequences collide in the trie.
        """
        self.data: _KeyQueueData = {}
        for s, result in sequences:
            if isinstance(result, dict):
                raise TypeError(result)
            self.add(self.data, s, result)

    def add(
        self,
        root: _KeyQueueData,
        s: str,
        result: str,
    ) -> None:
        """
        Add one ``(escape sequence, key name)`` pair to the trie.

        :raises RuntimeError: the sequence collides with a shorter one already in the trie.
        :raises ValueError: the sequence collides with a longer one already in the trie.
        """
        if not isinstance(root, MutableMapping) or not s:
            raise RuntimeError("trie conflict detected")

        seq_start = ord(s[0])
        if seq_start in root:
            child = root[seq_start]
            if isinstance(child, str):
                raise ValueError("trie conflict detected")

            self.add(child, s[1:], result)
            return
        if len(s) > 1:
            d: _KeyQueueData = {}
            root[seq_start] = d
            self.add(d, s[1:], result)
            return
        root[seq_start] = result

    def get(
        self,
        keys: list[int],
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str | _MouseInput | _CursorPosition | _TerminalReport | None, list[int]] | None:
        """Decode the longest key sequence matching the start of ``keys``, trying the trie then the special reports.

        :param keys: the codes after the ESC that starts the sequence.
        :param more_available: raise MoreInputRequired when the codes end in the middle of a sequence.
        :param csi_u_shift_applied: see `read_key_report`.
        :returns: the input and the codes left after it, with ``None`` as the input of a mouse report cut short;
            ``None`` when no sequence matches.
        """
        if (result := self._get_at(keys, 0, more_available, csi_u_shift_applied=csi_u_shift_applied)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _get_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str | _MouseInput | _CursorPosition | _TerminalReport | None, int] | None:
        """Do what :meth:`get` does for ``codes[start:]``, returning the position after the input.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        result: tuple[str | _MouseInput | _CursorPosition | _TerminalReport | None, int] | None
        if result := self._get_recurse_at(self.data, codes, start, more_available):
            return result

        for read_report in (
            self._read_private_mode_report_at,
            self._read_private_report_at,
            self._read_modify_keys_report_at,
            self._read_window_size_report_at,
            self._read_string_report_at,
        ):
            if (result := read_report(codes, start, more_available)) is not None:
                return result

        result = self._read_key_report_at(
            codes,
            start,
            more_available,
            csi_u_shift_applied=csi_u_shift_applied,
        )
        if result is not None:
            return result

        return self._read_cursor_position_at(codes, start, more_available)

    def get_recurse(
        self,
        root: (_KeyQueueData | str),
        keys: list[int],
        more_available: bool,
    ) -> tuple[str | _MouseInput | None, list[int]] | None:
        """
        Walk the trie for the next key, consuming codes as it goes.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._get_recurse_at(root, keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _get_recurse_at(
        self,
        root: (_KeyQueueData | str),
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[str | _MouseInput | None, int] | None:
        """Do what :meth:`get_recurse` does for ``codes[start:]``, returning the position after the input.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        node = root
        pos = start
        while isinstance(node, MutableMapping):
            if pos >= len(codes):
                # get more keys
                if more_available:
                    raise MoreInputRequired
                return None

            if codes[pos] not in node:
                return None

            node = node[codes[pos]]
            pos += 1

        if node == "mouse":
            return self._read_mouse_info_at(codes, pos, more_available)

        if node == "sgrmouse":
            return self._read_sgrmouse_info_at(codes, pos, more_available)

        return (node, pos)

    def read_mouse_info(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_MouseInput | None, list[int]] | None:
        """Read an X10 mouse report from the codes and return the resulting input.

        A report cut short is consumed and gives ``None`` as its input.
        It is cut short when the next ``ESC [ M`` report starts in place of one of its three bytes,
        or when the codes end after one or two of them.
        The FreeBSD ``vt(4)`` console sends such reports, since it leaves out a column or row past 94.

        :returns: the mouse event, or ``None`` for a report cut short, and the codes left after the report;
            ``None`` when the codes end right after ``ESC [ M``.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_mouse_info_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_mouse_info_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_MouseInput | None, int] | None:
        """Do what :meth:`read_mouse_info` does for ``codes[start:]``, returning the position after the report.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        # the three bytes of the report and the two after an ESC among them, the most this reads
        keys = codes[start : start + 5]
        # Any other byte below the offset is a coordinate the terminal wrapped past 255, as the Linux console does;
        # 27 is one too (column or row 250), so only a whole "ESC [ M" marks the next report.
        for i, k in enumerate(keys[:3]):
            if k == 27:
                following = tuple(keys[i + 1 : i + 3])
                if following == _NEXT_MOUSE_REPORT:
                    return None, start + i
                if more_available and len(following) < 2 and following == _NEXT_MOUSE_REPORT[: len(following)]:
                    raise MoreInputRequired
        if len(keys) < 3:
            if more_available:
                raise MoreInputRequired
            if keys:
                return None, len(codes)
            return None

        b = keys[0] - _MOUSE_BYTE_OFFSET
        # A terminal sends a byte, and one below the offset wraps to the end of the range, as xterm's NUL past its end.
        # A code above 255 can come only from an encoder not limited to bytes, such as the curses display,
        # and carries the coordinate itself.
        x, y = (k - _MOUSE_COORD_OFFSET if k > _MOUSE_BYTE_MAX else (k - _MOUSE_COORD_OFFSET) % 256 for k in keys[1:3])

        prefixes = [prefix for prefix, bit in _MOUSE_MODIFIER_PREFIXES if b & bit]
        multi_click = (b & MOUSE_MULTIPLE_CLICK_MASK) >> 9
        if multi_click == 1:
            prefixes.append("double ")
        elif multi_click == 2:
            prefixes.append("triple ")
        prefix = "".join(prefixes)

        button = _mouse_button(b)

        if (b & MouseBit.BUTTON) == MouseBit.BUTTON and not b & (MouseBit.HIGH_BUTTON | MouseBit.EXTRA_BUTTON):
            action = "release"
            button = 0
        elif b & MOUSE_RELEASE_FLAG:
            action = "release"
        elif b & MouseBit.DRAG:
            action = "drag"
        elif multi_click:
            action = "click"
        else:
            action = "press"

        return ((f"{prefix}mouse {action}", button, x, y), start + 3)

    def read_sgrmouse_info(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_MouseInput, list[int]] | None:
        """Read an SGR mouse report from the codes and return the resulting input.

        :returns: the mouse event and the codes left after the report,
            or None when the codes do not start with an SGR mouse report.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_sgrmouse_info_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_sgrmouse_info_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_MouseInput, int] | None:
        # Helpful links:
        # https://stackoverflow.com/questions/5966903/how-to-get-mousemove-and-mouseclick-in-bash
        # http://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
        """Do what :meth:`read_sgrmouse_info` does for ``codes[start:]``, returning the position after the report.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        # the longest body and its terminator, the most this reads
        keys = codes[start : start + _SGR_MOUSE_MAX_LEN + 1]
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None

        # Anything other than "Pb;Px;Py" digits before the terminator, or a longer run, is not a report: it is
        # rejected here instead of being buffered while waiting for a terminator that may never come.
        for pos_m in range(min(len(keys), _SGR_MOUSE_MAX_LEN + 1)):
            k = keys[pos_m]
            if k in {ord("M"), ord("m")}:
                break
            if not (_ORD_0 <= k <= _ORD_9 or k == ord(";")):
                return None
        else:
            if more_available and len(keys) <= _SGR_MOUSE_MAX_LEN:
                raise MoreInputRequired
            return None

        fields = bytes(keys[:pos_m]).split(b";")
        if len(fields) != 3 or not all(fields):
            return None
        b, x, y = (int(field) for field in fields)
        action = chr(keys[pos_m])
        # Double and triple clicks are not supported.
        # They can be implemented by using a timer.
        # This timer can check if the last registered click is below a certain threshold.
        # This threshold is normally set in the operating system itself,
        # so setting one here will cause an inconsistent behaviour.

        prefixes = [prefix for prefix, bit in _MOUSE_MODIFIER_PREFIXES if b & bit]
        prefix = "".join(prefixes)

        button = _mouse_button(b)
        x -= 1
        y -= 1

        if action == "M":
            if b & MouseBit.DRAG:
                action = "drag"
            else:
                action = "press"
        else:
            action = "release"

        return ((f"{prefix}mouse {action}", button, x, y), start + pos_m + 1)

    def read_private_mode_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_PrivateModeReport, list[int]] | None:
        """Interpret a DECRPM reply (CSI ? Pd ; Ps $ y).

        :returns: ``('private mode report', mode, value)``.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_private_mode_report_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_private_mode_report_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_PrivateModeReport, int] | None:
        """Do what :meth:`read_private_mode_report` does for ``codes[start:]``, returning the position after the reply.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        # "[?", at most _CSI_PARAMETERS_MAX_LEN parameter bytes and the final "$y": a longer run is not a report
        limit = _CSI_PARAMETERS_MAX_LEN + 4
        keys = codes[start : start + limit]
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[0] != ord("["):
            return None
        if len(keys) < 2:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[1] != ord("?"):
            return None
        more_available = more_available and len(keys) < limit
        # read the mode number
        mode = ""
        i = 2
        for k in keys[i:]:
            i += 1
            if k == ord(";"):
                if not mode:
                    return None
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            mode += chr(k)
        else:
            if more_available:
                raise MoreInputRequired
            return None
        if not keys[i:]:
            if more_available:
                raise MoreInputRequired
            return None
        # Ps: "0" is a valid value here (mode not recognized), unlike the mode number above.
        value = 0
        got_digit = False
        for k in keys[i:]:
            i += 1
            if k == ord("$"):
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            value = value * 10 + k - _ORD_0
            got_digit = True
        else:
            if more_available:
                raise MoreInputRequired
            return None
        if not got_digit:
            return None
        if not keys[i:]:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[i] != ord("y"):
            return None
        return (("private mode report", mode, value), start + i + 1)

    def read_cursor_position(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_CursorPosition, list[int]] | None:
        """
        Interpret cursor position information being sent by the user's terminal.

        :returns: ('cursor position', x, y) where (x, y) == (0, 0) is the top left of the screen.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_cursor_position_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_cursor_position_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_CursorPosition, int] | None:
        """Do what :meth:`read_cursor_position` does for ``codes[start:]``, returning the position after the report.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        # "[", at most _CSI_PARAMETERS_MAX_LEN parameter bytes and the final "R": a longer run is not a report
        limit = _CSI_PARAMETERS_MAX_LEN + 2
        keys = codes[start : start + limit]
        if not keys:
            if more_available:
                raise MoreInputRequired
            return None
        if keys[0] != ord("["):
            return None
        # read y value
        y = 0
        i = 1
        for k in keys[i:]:
            i += 1
            if k == ord(";"):
                if not y:
                    return None
                break
            if k < _ORD_0 or k > _ORD_9:
                return None
            if not y and k == _ORD_0:
                return None
            y = y * 10 + k - _ORD_0
        if not keys[i:]:
            if more_available and len(keys) < limit:
                raise MoreInputRequired
            return None
        # read x value
        x = 0
        for k in keys[i:]:
            i += 1
            if k == ord("R"):
                if not x:
                    return None
                return (("cursor position", x - 1, y - 1), start + i)
            if k < _ORD_0 or k > _ORD_9:
                return None
            if not x and k == _ORD_0:
                return None
            x = x * 10 + k - _ORD_0
        if not keys[i:] and more_available and len(keys) < limit:
            raise MoreInputRequired
        return None

    @staticmethod
    def _split_csi(
        keys: list[int],
        more_available: bool,
        introducer: bytes,
        final_bytes: Iterable[int],
    ) -> tuple[list[list[str]], int, list[int]] | None:
        """Split a control sequence that starts with *introducer* and ends with one of *final_bytes*.

        :returns: the parameters, each split into its sub-parameters, the final byte and the codes after it,
            or None when the codes do not start with such a sequence.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := KeyqueueTrie._split_csi_at(keys, 0, more_available, introducer, final_bytes)) is None:
            return None
        fields, final, end = split
        return fields, final, keys[end:]

    @staticmethod
    def _split_csi_at(
        codes: list[int],
        start: int,
        more_available: bool,
        introducer: bytes,
        final_bytes: Iterable[int],
    ) -> tuple[list[list[str]], int, int] | None:
        """Do what :meth:`_split_csi` does for ``codes[start:]``, returning the position after the sequence.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        # the introducer, the longest body and the final byte, the most this reads
        keys = codes[start : start + len(introducer) + _CSI_PARAMETERS_MAX_LEN + 1]
        if keys[: len(introducer)] != list(introducer[: len(keys)]):
            return None
        for pos in range(len(introducer), min(len(keys), len(introducer) + _CSI_PARAMETERS_MAX_LEN + 1)):
            k = keys[pos]
            if k in final_bytes:
                break
            if not (_ORD_0 <= k <= _ORD_9 or k in {ord(";"), ord(":")}):
                return None
        else:
            if more_available and len(keys) <= len(introducer) + _CSI_PARAMETERS_MAX_LEN:
                raise MoreInputRequired
            return None
        body = bytes(keys[len(introducer) : pos]).decode("ascii")
        return [field.split(":") for field in body.split(";")], keys[pos], start + pos + 1

    def read_private_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_KeyboardProtocolReport | _DeviceAttributesReport, list[int]] | None:
        """Interpret a kitty keyboard protocol flags reply (CSI ? flags u) or a Primary DA reply (CSI ? Ps ; ... c).

        An empty parameter of a Primary DA reply, which ECMA-48 allows, is left out of its parameters.

        >>> from urwid.display.escape import input_trie
        >>> input_trie.read_private_report(list(b"[?62;52;c"), more_available=False)
        (('device attributes', (62, 52)), [])

        :returns: ``('keyboard protocol report', flags)`` or ``('device attributes', parameters)``.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_private_report_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_private_report_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_KeyboardProtocolReport | _DeviceAttributesReport, int] | None:
        """Do what :meth:`read_private_report` does for ``codes[start:]``, returning the position after the reply.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := self._split_csi_at(codes, start, more_available, b"[?", (ord("u"), ord("c")))) is None:
            return None
        fields, final, end = split
        if any(len(field) != 1 for field in fields):
            return None
        if final == ord("c"):
            # an empty parameter names no attribute, as in kitty's CSI ? 62;52;c
            values = tuple(int(field[0]) for field in fields if field[0])
            return (("device attributes", values), end) if values else None
        if len(fields) != 1 or not fields[0][0]:
            return None
        return ("keyboard protocol report", int(fields[0][0])), end

    def read_modify_keys_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> tuple[_ModifyKeysReport, list[int]] | None:
        """Interpret xterm's reply to a key modifier options query (CSI > Pp ; Pv m, or CSI > Pp m).

        :returns: ``('modify keys report', resource, value)``, with value None when the reply omits it.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (result := self._read_modify_keys_report_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    def _read_modify_keys_report_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_ModifyKeysReport, int] | None:
        """Do what :meth:`read_modify_keys_report` does for ``codes[start:]``, returning the position after the reply.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := self._split_csi_at(codes, start, more_available, b"[>", (ord("m"),))) is None:
            return None
        fields, _final, end = split
        if len(fields) > 2 or any(len(field) != 1 for field in fields) or not fields[0][0]:
            return None
        value = int(fields[1][0]) if len(fields) == 2 and fields[1][0] else None
        return ("modify keys report", int(fields[0][0]), value), end

    def _read_window_size_report_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_WindowSizeReport, int] | None:
        """Interpret an in-band resize notification (CSI 48 ; rows ; columns ; height ; width t) at *start*.

        The height and width in pixels may be left out; when present, they are skipped without being read.
        Each value may carry sub-parameters after a colon, which are ignored, as mode 2048 asks of a client.
        A row or column count of 0 or above 65535 makes the notification invalid.
        A notification therefore carries no size a terminal device could not, see ``_WINDOW_SIZE_MAX``.

        :returns: ``('window size report', columns, rows)`` and the position after the report,
            or None when the codes at *start* are not such a report.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        if (split := self._split_csi_at(codes, start, more_available, b"[48;", (ord("t"),))) is None:
            return None
        fields, _final, end = split
        if len(fields) not in _WINDOW_SIZE_REPORT_LENGTHS or not (fields[0][0] and fields[1][0]):
            return None
        rows, cols = int(fields[0][0]), int(fields[1][0])
        if not (0 < rows <= _WINDOW_SIZE_MAX and 0 < cols <= _WINDOW_SIZE_MAX):
            return None
        return ("window size report", cols, rows), end

    def read_string_report(
        self,
        keys: list[int],
        more_available: bool,
    ) -> (
        tuple[_TerminalVersionReport | _TerminalCapabilitiesReport | _DefaultColorReport | _SettingReport, list[int]]
        | None
    ):
        r"""Interpret an XTVERSION, XTGETTCAP, DECRPSS, or OSC 10 or OSC 11 reply.

        - XTVERSION: DCS > | text ST.
        - XTGETTCAP: DCS 1 + r ... ST or DCS 0 + r ... ST, listing ``name=value`` pairs separated by ``;``, each part
          hex-encoded. The valid form gives each value, or only the name for a boolean capability; the invalid form
          names what the terminal does not know.
        - DECRPSS: DCS 1 $ r setting ST for a valid request, DCS 0 $ r setting ST for one the terminal refused.
        - OSC 10 or OSC 11: OSC 10 ; color ST or OSC 11 ; color ST, the default foreground or background color as an
          X11 color spec in the ``rgb:`` or ``rgba:`` form terminals answer with; BEL may end it instead of ST. A color
          in another form is no reply, so the codes are keys.

        >>> from urwid.display.escape import input_trie
        >>> input_trie.read_string_report(list(b"P>|XTerm(390)\x1b\\"), more_available=False)
        (('terminal version', 'XTerm(390)'), [])
        >>> input_trie.read_string_report(list(b"P1+r636f6c6f7273=323536;524742\x1b\\"), more_available=False)
        (('terminal capabilities', (('colors', '256'), ('RGB', ''))), [])
        >>> input_trie.read_string_report(list(b"P1$r0;48:2::135:175:215m\x1b\\"), more_available=False)
        (('setting report', True, '0;48:2::135:175:215m'), [])
        >>> input_trie.read_string_report(list(b"]11;rgb:ffff/ffff/ffff\x07"), more_available=False)
        (('default color', 11, 'rgb:ffff/ffff/ffff'), [])

        :param keys: the codes after the ESC that starts the reply.
        :param more_available: raise MoreInputRequired when the codes end in the middle of a reply.
        :returns: ``('terminal version', text)``, ``('terminal capabilities', ((name, value), ...))``,
            with value None for a capability the terminal does not know, ``('setting report', valid, setting)``,
            or ``('default color', number, color)``.
            A complete XTGETTCAP reply whose body cannot be read lists no capability, so it is not read as keys.
        :raises MoreInputRequired: the codes end in the middle of a reply and *more_available* is set.
        """
        if (result := self._read_string_report_at(keys, 0, more_available)) is None:
            return None
        decoded, end = result
        return decoded, keys[end:]

    @staticmethod
    def _read_string_report_at(
        codes: list[int],
        start: int,
        more_available: bool,
    ) -> tuple[_TerminalVersionReport | _TerminalCapabilitiesReport | _DefaultColorReport | _SettingReport, int] | None:
        """Do what :meth:`read_string_report` does for ``codes[start:]``, returning the position after the reply.

        Codes cut short after ``P`` or ``]`` alone are not waited for, since ESC P and ESC ] are also the keys
        :kbd:`Alt+Shift+P` and :kbd:`Alt+]`.

        :raises MoreInputRequired: the codes end in the middle of a reply and *more_available* is set.
        """
        for introducer in (
            _XTVERSION_INTRODUCER,
            *_XTGETTCAP_INTRODUCERS,
            *_DECRPSS_INTRODUCERS,
            *_DEFAULT_COLOR_INTRODUCERS,
        ):
            head = codes[start : start + len(introducer)]
            if head == list(introducer):
                break
            if (
                1 < len(head) < len(introducer)
                and start + len(head) == len(codes)
                and head == list(introducer[: len(head)])
            ):
                if more_available:
                    raise MoreInputRequired
                return None
        else:
            return None

        body_start = start + len(introducer)
        # the body, its ESC and the backslash of ST are the most this reads
        keys = codes[body_start : body_start + _STRING_REPORT_MAX_LEN + 2]
        if introducer in _DEFAULT_COLOR_INTRODUCERS:
            # chr(), as the codes include the curses key codes above 255
            seen = "".join(map(chr, keys[: max(map(len, _DEFAULT_COLOR_PREFIXES))]))
            if not any(seen.startswith(prefix) or prefix.startswith(seen) for prefix in _DEFAULT_COLOR_PREFIXES):
                # not waited for: the codes are keys
                return None
        if (esc := next((pos for pos, code in enumerate(keys) if not 0x20 <= code <= 0x7E), None)) is None:
            if more_available and len(keys) <= _STRING_REPORT_MAX_LEN:
                raise MoreInputRequired
            return None
        if esc > _STRING_REPORT_MAX_LEN:
            return None
        if introducer in _DEFAULT_COLOR_INTRODUCERS:
            color = bytes(keys[:esc]).decode("ascii")
            if not color.startswith(_DEFAULT_COLOR_PREFIXES):
                return None
            if keys[esc] == _BEL:
                # an OSC reply, which xterm ends as the query was ended, may end with BEL
                return ("default color", _DEFAULT_COLOR_INTRODUCERS[introducer], color), body_start + esc + 1
        if keys[esc] != 0x1B:
            return None
        if esc + 1 == len(keys):
            if more_available:
                raise MoreInputRequired
            return None
        if keys[esc + 1] != ord("\\"):
            return None
        body = bytes(keys[:esc]).decode("ascii")
        end = body_start + esc + 2
        if introducer == _XTVERSION_INTRODUCER:
            return ("terminal version", body), end
        if introducer in _DECRPSS_INTRODUCERS:
            return ("setting report", _DECRPSS_INTRODUCERS[introducer], body), end
        if introducer in _DEFAULT_COLOR_INTRODUCERS:
            return ("default color", _DEFAULT_COLOR_INTRODUCERS[introducer], body), end

        valid = introducer == _XTGETTCAP_VALID_INTRODUCER
        capabilities: list[tuple[str, str | None]] = []
        # an empty item, such as after the ";" that ends each name the Terminal widget answers, names nothing
        for item in filter(None, body.split(";")):
            name_hex, separator, value_hex = item.partition("=")
            # fromhex() would also take spaces between the digits
            if not (name_hex and _HEX_DIGITS.issuperset(name_hex) and _HEX_DIGITS.issuperset(value_hex)):
                return ("terminal capabilities", ()), end
            try:
                name = bytes.fromhex(name_hex).decode("ascii")
                value = bytes.fromhex(value_hex).decode("latin-1")
            except ValueError:  # an odd number of digits, or a name that is not ASCII
                return ("terminal capabilities", ()), end
            if not name.isprintable():
                return ("terminal capabilities", ()), end
            if not valid:
                capabilities.append((name, None))
            else:
                capabilities.append((name, value if separator else ""))
        return ("terminal capabilities", tuple(capabilities)), end

    def read_key_report(
        self,
        keys: list[int],
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str, list[int]] | None:
        """Interpret a key report the trie has no entry for.

        These are the kitty keyboard protocol's CSI u reports, xterm's modifyOtherKeys reports
        (CSI 27 ; modifiers ; code ~), and the legacy CSI number ; modifiers ~ and CSI 1 ; modifiers letter forms
        with modifiers beyond shift, alt and ctrl.

        :param keys: the codes after the ESC that starts the sequence.
        :param more_available: raise MoreInputRequired when the codes end in the middle of a sequence.
        :param csi_u_shift_applied: a CSI u report carries the character typed with shift, as xterm's modifyOtherKeys
            sends it with the formatOtherKeys resource set, rather than the kitty keyboard protocol's unshifted key.
        :returns: the key name, or None when the codes do not start with a key report urwid can name.
        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        result = self._read_key_report_at(
            keys,
            0,
            more_available,
            csi_u_shift_applied=csi_u_shift_applied,
        )
        if result is None:
            return None
        name, end = result
        return name, keys[end:]

    def _read_key_report_at(
        self,
        codes: list[int],
        start: int,
        more_available: bool,
        *,
        csi_u_shift_applied: bool = False,
    ) -> tuple[str, int] | None:
        """Do what :meth:`read_key_report` does for ``codes[start:]``, returning the position after the report.

        :raises MoreInputRequired: the codes end in the middle of a sequence and *more_available* is set.
        """
        final_bytes = (ord("u"), ord("~"), *_CSI_LETTER_KEYS)
        if codes[start + 1 : start + 2] and not _ORD_0 <= codes[start + 1] <= _ORD_9:
            # a key report starts with its key's number; a private parameter starts a terminal reply instead
            return None
        if (split := self._split_csi_at(codes, start, more_available, b"[", final_bytes)) is None:
            return None
        fields, final, end = split
        numbers = [[int(sub) if sub else None for sub in field] for field in fields]
        code, shifted_code = (numbers[0] + [None])[:2]
        modifiers = numbers[1][0] if len(numbers) > 1 and numbers[1][0] is not None else 1
        if code is None or modifiers < 1:
            return None
        modifiers -= 1

        name: str | None
        if final == ord("u"):
            if code in _CSI_U_KEYS:
                name = _modified_key_name(_CSI_U_KEYS[code], modifiers)
            else:
                name = _text_key_name(code, shifted_code, modifiers, shift_applied=csi_u_shift_applied)
        elif final == ord("~") and code == _MODIFY_OTHER_KEYS_NUMBER:
            if len(numbers) != 3 or (key_code := numbers[2][0]) is None:
                return None
            if key_code in _CSI_U_KEYS:
                name = _modified_key_name(_CSI_U_KEYS[key_code], modifiers)
            else:
                name = _text_key_name(key_code, None, modifiers, shift_applied=True)
        elif final == ord("~"):
            name = _modified_key_name(_CSI_TILDE_KEYS[code], modifiers) if code in _CSI_TILDE_KEYS else None
        else:
            name = _modified_key_name(_CSI_LETTER_KEYS[final], modifiers) if code == 1 else None

        if name is None:
            return None
        return name, end
