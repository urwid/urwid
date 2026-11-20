# Urwid terminal emulation canvas
#    Copyright (C) 2010  aszlig
#    Copyright (C) 2011  Ian Ward
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

"""Escape sequence parser of :class:`TermCanvas`, the top layer that completes the canvas."""

from __future__ import annotations

import types
import typing
from contextlib import suppress

from urwid import util, version
from urwid.ansi_parser import _CANCEL as CANCEL
from urwid.ansi_parser import _COMMAND_STRING_IGNORED as COMMAND_STRING_IGNORED
from urwid.ansi_parser import _COMMAND_STRING_OPENERS as COMMAND_STRING_OPENERS
from urwid.ansi_parser import (
    _OSC_STATES,
    _STRING_STATES,
    MAX_CSI_LENGTH,
    MAX_OSC_LENGTH,
    OSC_IGNORED_CONTROLS,
    ParseState,
    _csi_parameters,
    attrspec_with_hyperlink,
    resolve_osc_hyperlink,
    resolve_osc_title,
)
from urwid.canvas.term._cells import CHARSET_DEFAULT, CHARSET_UTF8, ESC_B, _drawn_width, _may_continue_cluster
from urwid.canvas.term._modes import _ModesCanvas
from urwid.canvas.term._rectangles import _RectanglesCanvas
from urwid.canvas.term._reports import (
    _DESIGNATED_CHARSETS,
    _PRIMARY_DEVICE_ATTRIBUTES,
    _SECONDARY_DEVICE_ATTRIBUTES,
    _TERTIARY_DEVICE_ATTRIBUTES,
    _ReportsCanvas,
)
from urwid.canvas.term._screen import _CONFORMANCE_LEVELS
from urwid.display._sgr import parse_sgr_parameters
from urwid.display.escape import _C0_CONTROLS, DCS, ST

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


#: :data:`urwid.ansi_parser.OSC_IGNORED_CONTROLS` as bytes
_OSC_IGNORED = frozenset(char.encode("ascii") for char in OSC_IGNORED_CONTROLS)
#: :data:`urwid.ansi_parser._CANCEL` as bytes
_CANCEL: typing.Final = frozenset(char.encode("ascii") for char in CANCEL)
#: :data:`urwid.ansi_parser._COMMAND_STRING_IGNORED` as bytes
_COMMAND_STRING_IGNORED: typing.Final = frozenset(char.encode("ascii") for char in COMMAND_STRING_IGNORED)


#: :data:`urwid.ansi_parser._COMMAND_STRING_OPENERS` as bytes
_COMMAND_STRING_OPENERS: typing.Final = frozenset(char.encode("ascii") for char in COMMAND_STRING_OPENERS)


#: the character set slot each intermediate byte of a 94-character set designation (ESC I F) selects
_DESIGNATED_SLOTS: typing.Final = types.MappingProxyType({b"(": 0, b")": 1, b"*": 2, b"+": 3})
#: the slot each intermediate byte of a 96-character set designation selects
_DESIGNATED_96_SLOTS: typing.Final = types.MappingProxyType({b"-": 1, b".": 2, b"/": 3})


#: the final bytes after ESC of the locking shifts into GR: LS1R, LS2R and LS3R
_GR_LOCKING_SHIFTS: typing.Final = types.MappingProxyType({b"~": 1, b"}": 2, b"|": 3})

#: the final bytes after ESC of the locking shifts LS2 and LS3 and the single shifts SS2 and SS3, with their slot
_LOCKING_SHIFTS: typing.Final = types.MappingProxyType({b"n": 2, b"o": 3})
_SINGLE_SHIFTS: typing.Final = types.MappingProxyType({b"N": 2, b"O": 3})

#: the control characters :meth:`TermCanvas.process_char` executes, also after an ESC inside an OSC string
_EXECUTED_CONTROLS = frozenset((b"\r", b"\x0f", b"\x0e", b"\n", b"\v", b"\f", b"\t", b"\b"))

#: the C0 control characters :meth:`TermCanvas.process_char` ignores: all but ESC, BEL, CAN, SUB and the executed ones
_IGNORED_CONTROLS = frozenset(bytes((code,)) for code in _C0_CONTROLS) - {ESC_B, b"\a", *_CANCEL} - _EXECUTED_CONTROLS


#: the private markers of the kitty keyboard protocol's CSI u sequences: query, push, pop and set the flags
_KITTY_KEYBOARD_MARKERS: typing.Final = frozenset((b"?", b">", b"<", b"="))


class CSIAlias(typing.NamedTuple):
    """Entry in :data:`CSI_COMMANDS` redirecting a CSI final byte to another command's byte."""

    alias_mark: str  # can not have constructor with default first and non-default second arg
    alias: bytes


class CSICommand(typing.NamedTuple):
    """Entry in :data:`CSI_COMMANDS` describing how to parse and dispatch one CSI sequence."""

    num_args: int
    default: int
    callback: Callable[[TermCanvas, list[int], bool], typing.Any]  # return value ignored


CSI_COMMANDS: dict[bytes, CSIAlias | CSICommand] = {
    # possible values:
    #     None -> ignore sequence
    #     CSICommand(<minimum number of args>, <fallback if no argument>, callback)
    #     CSIAlias("alias", <symbol>)
    #
    # while callback is executed as:
    #     callback(<instance of TermCanvas>, arguments, has_question_mark)
    b"@": CSICommand(1, 1, lambda s, number, q: s.insert_chars(chars=number[0])),
    b"A": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative=True)),
    b"B": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative=True)),
    b"C": CSICommand(1, 1, lambda s, cols, q: s.move_cursor(cols[0], 0, relative=True)),
    b"D": CSICommand(1, 1, lambda s, cols, q: s.move_cursor(-cols[0], 0, relative=True)),
    b"E": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, rows[0], relative_y=True)),
    b"F": CSICommand(1, 1, lambda s, rows, q: s.move_cursor(0, -rows[0], relative_y=True)),
    b"G": CSICommand(1, 1, lambda s, col, q: s.move_cursor(col[0] - 1, 0, relative_y=True)),
    b"H": CSICommand(2, 1, lambda s, x_y, q: s.move_cursor(x_y[1] - 1, x_y[0] - 1)),
    b"I": CSICommand(1, 1, lambda s, count, _q: s.csi_forward_tab(count[0])),
    b"J": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_display(mode[0], selective=q or s.modes.iso_protection)),
    b"K": CSICommand(1, 0, lambda s, mode, q: s.csi_erase_line(mode[0], selective=q or s.modes.iso_protection)),
    b"L": CSICommand(1, 1, lambda s, number, q: s.insert_lines(lines=number[0])),
    b"M": CSICommand(1, 1, lambda s, number, q: s.remove_lines(lines=number[0])),
    b"P": CSICommand(1, 1, lambda s, number, q: s.remove_chars(chars=number[0])),
    b"S": CSICommand(1, 1, lambda s, lines, q: s.csi_scroll(lines[0])),
    # SD (CSI Ps T) is run in parse_csi, which sees whether its parameter is 0
    b"T": CSICommand(0, 0, lambda s, none, q: None),
    # SD as ECMA-48 corrected it, which xterm takes too
    b"^": CSICommand(1, 1, lambda s, lines, q: s.csi_scroll(lines[0], reverse=True)),
    b"X": CSICommand(
        1,
        1,
        lambda s, number, q: s.erase(
            s.term_cursor,
            (s.term_cursor[0] + number[0] - 1, s.term_cursor[1]),
            selective=s.modes.iso_protection,
        ),
    ),
    b"Z": CSICommand(1, 1, lambda s, count, _q: s.csi_backward_tab(count[0])),
    b"a": CSIAlias("alias", b"C"),
    b"b": CSICommand(1, 1, lambda s, count, _q: s.csi_repeat(count[0])),
    b"c": CSICommand(0, 0, lambda s, none, q: s.csi_get_device_attributes(q)),
    b"d": CSICommand(1, 1, lambda s, row, q: s.move_cursor(0, row[0] - 1, relative_x=True)),
    b"e": CSIAlias("alias", b"B"),
    b"f": CSIAlias("alias", b"H"),
    b"g": CSICommand(1, 0, lambda s, mode, q: s.csi_clear_tabstop(mode[0])),
    b"h": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q)),
    b"l": CSICommand(1, 0, lambda s, modes, q: s.csi_set_modes(modes, q, reset=True)),
    # SGR (CSI Pm m) is run in parse_csi, which also reads its sub-parameters
    b"m": CSICommand(0, 0, lambda s, _none, _q: None),
    b"n": CSICommand(1, 0, lambda s, mode, q: s.csi_status_report(mode[0], private=q)),
    # DECRQM (CSI ? Ps $ p, CSI Ps $ p), DECSTR (CSI ! p) and DECSCL (CSI Ps ; Ps " p) are run in parse_csi, and the
    # other forms are not implemented
    b"p": CSICommand(0, 0, lambda s, none, q: None),
    b"q": CSICommand(1, 0, lambda s, mode, q: s.csi_set_keyboard_leds(mode[0])),
    b"r": CSICommand(2, 0, lambda s, t_b, q: s.csi_set_scroll(t_b[0], t_b[1])),
    # SCOSC and SCORC save and restore what DECSC and DECRC do, as in xterm and the Linux console
    b"s": CSICommand(0, 0, lambda s, none, q: s.save_cursor(with_attrs=True)),
    b"u": CSICommand(0, 0, lambda s, none, q: s.restore_cursor(with_attrs=True)),
    # DECRQPSR (CSI Ps $ w) is answered in parse_csi, and the other forms are not implemented
    b"w": CSICommand(0, 0, lambda s, none, q: None),
    # the VT420 sequences with an intermediate byte, run in parse_csi from _INTERMEDIATE_COMMANDS: DECRQDE (CSI " v),
    # DECFRA (CSI ... $ x), DECERA (CSI ... $ z), DECSERA (CSI ... $ {), DECCRA (CSI ... $ v), DECCARA (CSI ... $ r),
    # DECRARA (CSI ... $ t), DECSACE (CSI Ps * x), DECRQCRA (CSI ... * y), DECIC (CSI Ps ' }) and DECDC (CSI Ps ' ~);
    # DECSCA (CSI Ps " q) and DECRQUPSS (CSI & u) are run there too
    b"t": CSICommand(1, 0, lambda s, operation, q: s.csi_report_window(operation[0])),
    b"v": CSICommand(0, 0, lambda s, none, q: None),
    b"x": CSICommand(0, 0, lambda s, none, q: None),
    b"y": CSICommand(0, 0, lambda s, none, q: None),
    b"z": CSICommand(0, 0, lambda s, none, q: None),
    b"{": CSICommand(0, 0, lambda s, none, q: None),
    b"}": CSICommand(0, 0, lambda s, none, q: None),
    b"~": CSICommand(0, 0, lambda s, none, q: None),
    b"`": CSIAlias("alias", b"G"),
}


#: the final bytes whose "?" form is run: the DEC private modes, the linux cursor style CSI ? Ps c (not answered), the
#: selective erases DECSED and DECSEL, and the DEC status reports, which csi_status_report() answers with their own
#: replies; any other "?" form, such as the kitty keyboard protocol query CSI ? u, is a different command than the one
#: without it
_CSI_PRIVATE_FINAL_BYTES: typing.Final = frozenset((b"J", b"K", b"c", b"h", b"l", b"n"))


class TermCanvas(_ReportsCanvas, _RectanglesCanvas, _ModesCanvas):
    """Canvas holding a terminal's screen and scrollback content, for the widget that owns it."""

    __slots__ = ()

    @property
    def escbuf(self) -> bytes:
        """Return the buffered bytes of the escape sequence being parsed."""
        return bytes(self._escbuf)

    @escbuf.setter
    def escbuf(self, value: bytes) -> None:
        self._escbuf = bytearray(value)

    @property
    def reads_utf8(self) -> bool:
        """Whether input bytes are decoded as UTF-8.

        They are when the data selected UTF-8 (``ESC % G``) or urwid's encoding is UTF-8.
        Otherwise each byte is one character in urwid's encoding.
        """
        return self.modes.main_charset == CHARSET_UTF8 or util.get_encoding_mode() == "utf8"

    def addstr(self, data: Iterable[int]) -> None:
        """Feed a sequence of input bytes through the terminal parser, one byte at a time."""
        if self.width <= 0 or self.height <= 0:
            # not displayable, do nothing!
            return

        if self.scrolling_up and self.scroll_on_output and data:
            self.scroll_buffer(reset=True)
        for byte in data:
            self.addbyte(byte)

    def set_g01(self, char: bytes, mod: bytes) -> None:
        """Designate the character set of final byte *char* to the slot of intermediate byte *mod*.

        The slots are G0 for ``(``, G2 for ``*``, G3 for ``+`` and G1 for any other byte.
        """
        if self.modes.main_charset != CHARSET_DEFAULT:
            return

        g = _DESIGNATED_SLOTS.get(mod, 1)
        self.charset.define(g, _DESIGNATED_CHARSETS.get(char, "default"), final=char)

    def parse_csi(self, char: bytes) -> None:
        """Parse ECMA-48 CSI (Control Sequence Introducer) sequences."""
        if char == b"u" and (marker := bytes(self._escbuf[:1])) in _KITTY_KEYBOARD_MARKERS:
            if (params := _csi_parameters(self._escbuf[1:])) is not None:
                self.csi_keyboard_flags(marker, params)
            return

        if char == b"p" and self._escbuf.endswith(b"$"):
            # DECRQM for a DEC private mode, CSI ? Ps $ p, or an ANSI mode, CSI Ps $ p
            if self._escbuf.startswith(b"?"):
                if (mode := self._escbuf[1:-1]).isdigit():
                    self.csi_report_private_mode(int(mode))
            elif (mode := self._escbuf[:-1]).isdigit():
                self.csi_report_mode(int(mode))
            return

        if char == b"c" and bytes(self._escbuf) in {b"=", b"=0"}:
            # Tertiary DA: CSI = c, a DCS reply, which a VT100 (level 61) does not send
            if self.conformance_level > 61:
                self.widget.respond(_TERTIARY_DEVICE_ATTRIBUTES)
            return

        if (handler := _INTERMEDIATE_COMMANDS.get((bytes(self._escbuf[-1:]), char))) is not None:
            if (params := _csi_parameters(self._escbuf[:-1])) is not None:
                handler(self, params)
            return

        if char == b"T":
            # SD: as in xterm, which takes more parameters as its mouse highlight tracking, only no parameter or one
            # other than 0 scrolls
            if not self._escbuf or (self._escbuf.isdigit() and int(self._escbuf) > 0):
                self.csi_scroll(int(self._escbuf or b"1"), reverse=True)
            return

        if char == b"p" and self._escbuf == b"!":
            # DECSTR: CSI ! p
            self.soft_reset()
            return

        if char == b"p" and self._escbuf.endswith(b'"'):
            # DECSCL: CSI Ps1 ; Ps2 " p; Ps2 chooses 7-bit or 8-bit controls, and only 7-bit ones are sent
            level, *_controls = self._escbuf[:-1].split(b";")
            if level.isdigit() and int(level) in _CONFORMANCE_LEVELS:
                self.soft_reset()
                self.conformance_level = int(level)
            return

        if char == b"w" and self._escbuf.endswith(b"$"):
            # DECRQPSR: CSI Ps $ w, which a VT100 (level 61) does not answer
            if (report := self._escbuf[:-1]).isdigit() and self.conformance_level > 61:
                self.csi_report_presentation_state(int(report))
            return

        if char == b"c" and bytes(self._escbuf) in {b">", b">0"}:
            # Secondary DA: CSI > c
            self.widget.respond(_SECONDARY_DEVICE_ATTRIBUTES)
            return

        if char == b"q" and bytes(self._escbuf) in {b">", b">0"}:
            # XTVERSION, the query of the terminal's name and version
            self.widget.respond(f"{DCS}>|urwid({version.version}){ST}")
            return

        if char == b"m" and not self._escbuf.strip(b"0123456789;:"):
            self.csi_set_attr(parse_sgr_parameters(self._escbuf.decode("ascii")))
            return

        qmark = self._escbuf.startswith(b"?")
        body = self._escbuf[1 if qmark else 0 :]
        escbuf = _csi_parameters(body)
        if escbuf is None or (qmark and char not in _CSI_PRIVATE_FINAL_BYTES):
            # sub-parameters, other private markers and intermediate bytes select sequences not implemented here
            return

        if (cmd_ := CSI_COMMANDS[char]) is not None:
            if isinstance(cmd_, CSIAlias):
                csi_cmd: CSICommand = CSI_COMMANDS[cmd_.alias]  # type: ignore[assignment]
            else:
                csi_cmd = cmd_

            number_of_args, default_value, cmd = csi_cmd
            while len(escbuf) < number_of_args:
                escbuf.append(default_value)
            for i in range(len(escbuf)):
                if escbuf[i] is None or escbuf[i] == 0:
                    escbuf[i] = default_value

            with suppress(ValueError):
                cmd(self, typing.cast("list[int]", escbuf), qmark)
                # ignore arguments that the command's callback rejects.

    def parse_noncsi(self, char: bytes, mod: bytes = b"") -> None:
        """Parse escape sequences which are not CSI."""
        if mod == b"#" and char == b"8":
            self.decaln()
        elif mod == b"#":
            # the single-character sequences below take no intermediate byte
            pass
        elif mod == b"%":  # select main character set
            if char == b"@":
                self.modes.main_charset = CHARSET_DEFAULT
            elif char in b"G8":
                # 8 is obsolete and only for backwards compatibility
                self.modes.main_charset = CHARSET_UTF8
        elif mod in _DESIGNATED_SLOTS:  # define G0 to G3
            self.set_g01(char, mod)
        elif mod in _DESIGNATED_96_SLOTS:
            # a 96-character set, such as ISO Latin-1 (A), for G1 to G3: drawn as the default set and reported by DECCIR
            if self.modes.main_charset == CHARSET_DEFAULT:
                self.charset.define(_DESIGNATED_96_SLOTS[mod], "default", final=char, size96=True)
        elif mod:
            # another intermediate byte, such as S7C1T/S8C1T (ESC SP F, ESC SP G): accepted and not applied
            pass
        elif char in _GR_LOCKING_SHIFTS:
            self.charset.gr = _GR_LOCKING_SHIFTS[char]
        elif char == b"6":  # DECBI
            self.back_index()
        elif char == b"9":  # DECFI
            self.forward_index()
        elif char in _LOCKING_SHIFTS:
            self.charset.activate(_LOCKING_SHIFTS[char])
        elif char in _SINGLE_SHIFTS:
            self.charset.single_shift(_SINGLE_SHIFTS[char])
        elif char in {b"=", b">"}:  # DECKPAM, DECKPNM
            self.modes.keypad_application = char == b"="
        elif char == b"M":  # reverse line feed
            self.linefeed(reverse=True)
        elif char == b"D":  # line feed
            self.linefeed()
        elif char == b"c":  # reset terminal
            self.reset()
        elif char == b"E":  # newline
            self.newline()
        elif char == b"H":  # set tabstop
            self.set_tabstop()
        elif char == b"V":  # SPA
            self.protected = self.modes.iso_protection = True
        elif char == b"W":  # EPA, which also ends what DECSCA protects
            self.protected = False
        elif char == b"Z":  # DECID
            self.widget.respond(_PRIMARY_DEVICE_ATTRIBUTES)
        elif char == b"7":  # save current state
            self.save_cursor(with_attrs=True)
        elif char == b"8":  # restore current state
            self.restore_cursor(with_attrs=True)

    def parse_osc(self, buf: bytes) -> None:
        """Parse operating system command: a window title, or an OSC 8 hyperlink for the text written after it.

        The OSC bodies are recognised by :func:`urwid.ansi_parser.resolve_osc_title` and
        :func:`urwid.ansi_parser.resolve_osc_hyperlink`, shared with :class:`~urwid.ANSIText`.
        An invalid OSC 8 command ends the current link, so the text after it does not point at the previous target;
        :meth:`parse_escape` ends it for an over-long one, which never reaches this method.
        The body is in the encoding :meth:`addbyte` passes characters on in, and as in tmux, a title that is not
        valid in it is not set.
        A string that had a sequence that is not valid UTF-8, in UTF-8 mode, sets no title and ends the current link.

        :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
        """
        encoding = util.get_encoding()
        try:
            body = buf.decode(encoding)
        except UnicodeDecodeError:
            # still recognised, so an OSC 8 command ends the current link below
            body = buf.decode(encoding, "replace")
            valid = False
        else:
            valid = True
        title = resolve_osc_title(body)
        if title is not None:
            if valid and not self._osc_invalid_utf8:
                self.widget.set_title(title)
            return
        try:
            link = resolve_osc_hyperlink(body)
        except ValueError:
            link = None
        else:
            if link is None:
                return
            if self._osc_invalid_utf8:
                link = None
        self.attrspec = attrspec_with_hyperlink(self.attrspec, link, unset_color="default")

    def parse_dcs(self, body: bytes) -> None:
        """Apply the DCS string *body*, given without its ``ESC P`` and ST framing.

        DECRQSS and XTGETTCAP are answered and DECRSPS is applied.
        As in xterm, at the VT100 level (61) DECRSPS is not applied, and DECRQSS does not answer the conformance level.
        Any other DCS string is ignored.
        """
        if body.startswith(b"$q"):
            if not (self.conformance_level == _CONFORMANCE_LEVELS[0] and body[2:] == b'"p'):
                self.dcs_request_setting(body[2:])
        elif body.startswith(b"+q"):
            self.dcs_request_termcap(body[2:])
        elif self.conformance_level == _CONFORMANCE_LEVELS[0]:
            return
        elif body.startswith(b"1$t"):
            self.dcs_restore_cursor_information(body[3:])
        elif body.startswith(b"2$t"):
            self.dcs_restore_tab_stops(body[3:])

    def parse_escape(self, char: bytes) -> None:
        """Feed *char* through the escape-sequence state machine, dispatching to CSI/OSC/non-CSI parsing as needed."""
        if self.parsestate == ParseState.CSI:
            # within CSI
            if char in CSI_COMMANDS:
                if len(self._escbuf) < MAX_CSI_LENGTH:
                    self.parse_csi(char)
                self.parsestate = ParseState.ESCAPE
            elif b" " <= char <= b"?":  # parameter and intermediate bytes, ECMA-48 5.4
                # past the limit the parameters are dropped, and the sequence is skipped by its length
                if len(self._escbuf) < MAX_CSI_LENGTH:
                    self._escbuf += char
                return
        elif self.parsestate == ParseState.ESCAPE and char == b"]":
            # start of OSC
            self._escbuf = bytearray()
            self._osc_invalid_utf8 = False
            self.parsestate = ParseState.OSC  # pylint: disable=redefined-variable-type  # members of one enum
            return
        elif self.parsestate == ParseState.ESCAPE and char in _COMMAND_STRING_OPENERS:
            # start of a DCS, SOS, PM or APC string; the opening byte is kept, to tell a DCS from the others at ST
            self._escbuf = bytearray(char)
            self.parsestate = ParseState.COMMAND_STRING
            return
        elif self.parsestate in _STRING_STATES and self._escbuf[-1:] == ESC_B and char != b"\\":
            # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the string
            # unapplied and starts a new escape sequence
            self.leave_escape()
            self.within_escape = True
            self.process_char(char)
            return
        elif self.parsestate == ParseState.OSC_OVERFLOW and (
            char == b"\a" or (self._escbuf == ESC_B and char == b"\\")
        ):
            # end of an over-long OSC string, discarded
            pass
        elif self.parsestate == ParseState.COMMAND_STRING and self._escbuf[-1:] == ESC_B and char == b"\\":
            # end of a DCS, SOS, PM or APC string; only a DCS that was kept whole is applied
            if self._escbuf.startswith(b"P") and len(self._escbuf) < MAX_OSC_LENGTH:
                self.parse_dcs(bytes(self._escbuf[1:-1]))
        elif self.parsestate == ParseState.COMMAND_STRING:
            if len(self._escbuf) < MAX_OSC_LENGTH:
                self._escbuf += char
            else:
                # past the limit only the last byte is replaced, which is enough to recognise ST, also when *char* is a
                # multibyte character, so the buffer does not grow
                self._escbuf[-1:] = char[-1:]
            return
        elif self.parsestate == ParseState.OSC and char == b"\a":
            # end of OSC
            self.parse_osc(bytes(self._escbuf.lstrip(b"0")))
        elif self.parsestate == ParseState.OSC and self._escbuf[-1:] + char == ST.encode("iso8859-1"):
            # end of OSC
            self.parse_osc(bytes(self._escbuf[:-1].lstrip(b"0")))
        elif self.parsestate == ParseState.OSC and not self._escbuf and char == b"R":
            # reset palette
            pass
        elif self.parsestate in _OSC_STATES:
            if self.parsestate == ParseState.OSC and len(self._escbuf) < MAX_OSC_LENGTH:
                self._escbuf += char
                # an ESC is no digit: the next byte decides whether it starts ST or a new sequence
                if char != ESC_B and self._escbuf.startswith(b"P") and len(self._escbuf) == 8:
                    # the Linux console's palette set, ESC ] P n rr gg bb, ends with its 7th hex digit; not applied
                    self.leave_escape()
            else:
                if self.parsestate == ParseState.OSC and self._escbuf.lstrip(b"0").startswith(b"8;"):
                    # an over-long OSC 8 is refused like any other invalid one, ending the current link
                    self.attrspec = attrspec_with_hyperlink(self.attrspec, None, unset_color="default")
                # the rest of an over-long OSC string: only the last byte is kept,
                # which is enough to recognise either terminator
                self.parsestate = ParseState.OSC_OVERFLOW
                self._escbuf = bytearray(char)
            return
        elif self.parsestate == ParseState.ESCAPE and char == b"[":
            # start of CSI
            self._escbuf = bytearray()
            self.parsestate = ParseState.CSI
            return
        elif self.parsestate in {ParseState.ESCAPE, ParseState.ESC_INTERMEDIATE} and b" " <= char <= b"/":
            # an intermediate byte of an escape sequence (ECMA-35), such as the "(" of a G0 designation; past the
            # limit the intermediate bytes are dropped, and the sequence still ends at its final byte
            if self.parsestate == ParseState.ESCAPE:
                self._escbuf = bytearray()
                self.parsestate = ParseState.ESC_INTERMEDIATE
            if len(self._escbuf) < MAX_CSI_LENGTH:
                self._escbuf += char
            return
        elif self.parsestate == ParseState.ESC_INTERMEDIATE:
            self.parse_noncsi(char, bytes(self._escbuf))
        elif char in {
            b"c",
            b"D",
            b"E",
            b"H",
            b"M",
            b"V",
            b"W",
            b"Z",
            b"7",
            b"6",
            b"8",
            b"9",
            b">",
            b"=",
            *_LOCKING_SHIFTS,
            *_SINGLE_SHIFTS,
            *_GR_LOCKING_SHIFTS,
        }:
            self.parse_noncsi(char)

        self.leave_escape()

    def leave_escape(self) -> None:
        """Reset the escape-sequence parser state, discarding any sequence being read."""
        self.within_escape = False
        self.parsestate = ParseState.ESCAPE
        self._escbuf = bytearray()
        self._osc_invalid_utf8 = False

    def get_utf8_len(self, bytenum: int) -> int:
        """Process startbyte and return the number of bytes following it to get a valid UTF-8 multibyte sequence.

        :param bytenum: an integer ordinal
        """
        length = 0

        while bytenum & 0x40:
            bytenum <<= 1
            length += 1

        return length

    def addbyte(self, byte: int) -> None:
        """Parse main charset and add the processed byte(s) to the terminal state machine.

        :param byte: an integer ordinal
        """
        if self.reads_utf8:
            continuation = 0x80 <= byte < 0xC0
            pending = self.utf8_eat_bytes is not None
            # A lone continuation byte, or a sequence cut short by a byte that does not continue it, is not valid UTF-8,
            # and parse_osc() refuses an OSC string that had one.
            if self.parsestate == ParseState.OSC and continuation != pending:
                self._osc_invalid_utf8 = True
            if byte >= 0xC0:
                # start multibyte sequence
                self.utf8_eat_bytes = self.get_utf8_len(byte)
                self.utf8_buffer = bytearray([byte])
                return
            if 0x80 <= byte < 0xC0 and self.utf8_eat_bytes is not None:
                if self.utf8_eat_bytes > 1:
                    # continue multibyte sequence
                    self.utf8_eat_bytes -= 1
                    self.utf8_buffer.append(byte)
                    return

                # end multibyte sequence
                self.utf8_eat_bytes = None

                if sequence := (self.utf8_buffer + bytes([byte])).decode("utf-8", "ignore"):
                    if self.within_escape:
                        # an escape sequence takes bytes, not cells: no DEC drawing character here
                        char = sequence.encode(util.get_encoding(), "urwid_fallback_ascii")
                    elif "\x80" <= sequence < "\xa0" and not (self.charset.ibmpc_mapped or self.modes.display_ctrl):
                        # as in xterm, a C1 control written in UTF-8 is neither run nor drawn; the IBM PC mapping and
                        # display control mode draw it
                        return
                    else:
                        char, charsets = util.apply_target_encoding(sequence)
                        if charsets == [("0", 1)]:
                            # a DEC drawing character, or a fallback to one: one cell in the DEC character set
                            self.push_cursor(char, dec_special=True)
                            return
                        if char == b"\x9b":
                            # A character whose byte in urwid's encoding is 0x9B (U+203A in cp1252, U+042B in cp866)
                            # is a cell, as the display draws that byte; process_char() would run it as CSI.
                            self.push_cursor(char)
                            return
                        if "\x80" <= sequence < "\xa0":
                            # left to push_cursor(), as the IBM PC mapping draws it
                            width = 1
                        else:
                            width = _drawn_width(char)
                            # most characters start a cluster, which is known without looking at the cell before them
                            if (width == 0 or _may_continue_cluster(sequence)) and self.combine_char(
                                char,
                                sequence,
                                width=width,
                            ):
                                return
                        if width == 0:
                            # a character with no width that joins no character has no cell to take
                            return
                        if width == 2:
                            self.push_wide_char(char)
                            return

                else:
                    # an invalid multibyte sequence is dropped, and parse_osc() refuses an OSC string that had one
                    if self.parsestate == ParseState.OSC:
                        self._osc_invalid_utf8 = True
                    return
            else:
                self.utf8_eat_bytes = None
                if continuation and not (self.modes.display_ctrl and byte < 0xA0):
                    # A lone continuation byte is not valid UTF-8 and is dropped, as in xterm. That includes 0x9B and
                    # bytes inside an escape sequence. Display control mode shows the C1 controls in that range.
                    return
                char = bytes([byte])
        else:
            # a sequence pending when urwid's encoding stopped being UTF-8 is not continued by bytes read in another one
            self.utf8_eat_bytes = None
            char = bytes([byte])

        self.process_char(char)

    def process_char(self, char: int | bytes) -> None:
        """
        Process a single character (single- and multi-byte).

        :param char: a byte string
        """
        x, y = self.term_cursor

        if isinstance(char, int):
            char = char.to_bytes(1, "little")

        dc = self.modes.display_ctrl
        # as in xterm, REP repeats only a character written just before it: a control character, or a control function
        # such as SGR, between them cancels the repeat
        graphic, self._last_graphic = self._last_graphic, None
        if not self.within_escape or char < b" " or char == b"\x7f":
            self._repeat_graphic = None

        if char == ESC_B and self.parsestate not in _STRING_STATES:  # escape
            # as in a terminal, an ESC drops a sequence still being read and starts a new one
            self.leave_escape()
            self.within_escape = True
            self._repeat_graphic = graphic
        elif self.parsestate in _STRING_STATES and char in _CANCEL:
            # CAN/SUB abort a command string, also with display_ctrl
            self.leave_escape()
        elif (
            self.parsestate in _STRING_STATES
            and char in (_COMMAND_STRING_IGNORED if self.parsestate == ParseState.COMMAND_STRING else _OSC_IGNORED)
            and (self._escbuf[-1:] != ESC_B or dc or char not in _EXECUTED_CONTROLS)
        ):
            # as in a terminal, such a control character inside a command string is neither executed nor part of its
            # body; after an ESC, one of _EXECUTED_CONTROLS is executed by the branches below, and the ESC stays pending
            pass
        elif not dc and char == b"\r":  # carriage return CR
            self.carriage_return()
        elif not dc and char == b"\x0f":  # activate G0
            self.charset.activate(0)
        elif not dc and char == b"\x0e":  # activate G1
            self.charset.activate(1)
        elif not dc and char in b"\n\v\f":  # line feed LF/VT/FF
            self.linefeed()
            if self.modes.lfnl:
                self.carriage_return()
        elif not dc and char == b"\t":  # char tab
            self.tab()
        elif not dc and char == b"\b":  # backspace BS
            if x > 0:
                self.set_term_cursor(x - 1, y)
            self.is_rotten_cursor = False
        elif not dc and char == b"\a" and self.parsestate not in _OSC_STATES:  # BEL
            # inside an OSC string, also once over-long, BEL is its terminator
            self.widget.beep()
        elif not dc and char in _CANCEL:  # CAN/SUB
            self.leave_escape()
        elif not dc and (char in _IGNORED_CONTROLS or (char == b"\x7f" and self.parsestate not in _OSC_STATES)):
            # as in a terminal, any other C0 control character and DEL are ignored, and an escape sequence continues
            pass
        elif not dc and char == b"\x9b" and self.parsestate not in _STRING_STATES:  # CSI (equivalent to "ESC [")
            # like ESC, it drops a sequence still being read; inside a command string it is part of the string
            self.leave_escape()
            self.within_escape = True
            self.parsestate = ParseState.CSI
            self._repeat_graphic = graphic
        elif self.within_escape:
            self.parse_escape(char)
        else:
            self.push_cursor(char)


#: the CSI sequences with an intermediate byte before the final one, by intermediate and final byte, run with their
#: parameters, None for an empty one
_INTERMEDIATE_COMMANDS: typing.Final[Mapping[tuple[bytes, bytes], Callable[[TermCanvas, list[int | None]], None]]] = (
    types.MappingProxyType(
        {
            (b'"', b"v"): TermCanvas.csi_report_displayed_extent,
            (b"$", b"x"): TermCanvas.csi_fill_rectangle,
            (b"$", b"z"): TermCanvas.csi_erase_rectangle,
            (b"$", b"{"): TermCanvas.csi_selective_erase_rectangle,
            (b"$", b"r"): TermCanvas.csi_change_area_attributes,
            (b"$", b"t"): TermCanvas.csi_reverse_area_attributes,
            (b"*", b"x"): TermCanvas.csi_select_attribute_extent,
            (b'"', b"q"): TermCanvas.csi_select_protection,
            (b"&", b"u"): TermCanvas.csi_request_user_preferred_supplemental_set,
            (b"$", b"v"): TermCanvas.csi_copy_rectangle,
            (b"*", b"y"): TermCanvas.csi_request_checksum,
            (b"'", b"}"): TermCanvas.csi_insert_columns,
            (b"'", b"~"): TermCanvas.csi_delete_columns,
            (b" ", b"q"): TermCanvas.csi_set_cursor_style,
        }
    )
)
