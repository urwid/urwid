# Urwid escape-sequence state machine
#    Copyright (C) 2026  urwid contributors
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

"""The escape-sequence state machine of the ANSI parser and the terminal canvas: framing of sequences and strings.

The machine follows the DEC VT500 parser model (ground, escape, CSI, OSC and command-string states, with C0 controls
executed inside sequences), in the states :class:`~urwid.ansi_parser.ParseState` names.
It frames sequences and calls hook methods; what a sequence does is up to the class that inherits it.
:class:`~urwid.ansi_parser.AnsiParser` feeds it ``str`` and :class:`~urwid.TermCanvas` feeds it ``bytes``.
"""

from __future__ import annotations

import typing

from urwid.ansi_parser._grammar import (
    _CANCEL,
    _COMMAND_STRING_IGNORED,
    _COMMAND_STRING_OPENERS,
    _COMMAND_STRING_STATES,
    _OSC_STATES,
    _STRING_STATES,
    MAX_CSI_LENGTH,
    MAX_OSC_LENGTH,
    OSC_IGNORED_CONTROLS,
    ParseState,
)

if typing.TYPE_CHECKING:
    import re

#: the inheriting class's text type: a character it feeds is one, and so is a buffer of them
_TextT = typing.TypeVar("_TextT", str, bytes)

#: the code points of the escape-sequence grammar, compared against the code of each token
_ESC: typing.Final = 0x1B
_BEL: typing.Final = 0x07
_DEL: typing.Final = 0x7F
_BACKSLASH: typing.Final = 0x5C
_PALETTE_RESET: typing.Final = 0x52  # "R", the Linux console's OSC R
_CANCEL_CODES: typing.Final = frozenset(map(ord, _CANCEL))
_OSC_IGNORED_CODES: typing.Final = frozenset(map(ord, OSC_IGNORED_CONTROLS))
_COMMAND_STRING_IGNORED_CODES: typing.Final = frozenset(map(ord, _COMMAND_STRING_IGNORED))
#: the C0 controls and DEL executed outside a command string, also inside an escape sequence, which then continues
_EXECUTED_CODES: typing.Final = frozenset((*range(0x20), 0x7F)) - {_ESC} - _CANCEL_CODES
#: the final bytes after ESC that open a DCS, SOS, PM and APC string
_STRING_OPENER_CODES: typing.Final = frozenset(map(ord, _COMMAND_STRING_OPENERS))
#: the length of the Linux console's palette OSC, ``P n rr gg bb``
_PALETTE_SET_LENGTH: typing.Final = 8

# the states as module constants, which the per-character path reads faster than enum class attributes
_ESCAPE: typing.Final = ParseState.ESCAPE
_CSI: typing.Final = ParseState.CSI
_OSC: typing.Final = ParseState.OSC
_ESC_INTERMEDIATE: typing.Final = ParseState.ESC_INTERMEDIATE
_OSC_OVERFLOW: typing.Final = ParseState.OSC_OVERFLOW
_COMMAND_STRING: typing.Final = ParseState.COMMAND_STRING
_COMMAND_STRING_OVERFLOW: typing.Final = ParseState.COMMAND_STRING_OVERFLOW


class _VTParser(typing.Generic[_TextT]):
    """Escape-sequence state machine, fed one token at a time with :meth:`_vt_step`.

    A token is a character in the inheriting class's own text type: a one-character ``str``, or ``bytes`` in a
    terminal's encoding. The machine reads only its code, and keeps the token in that type in :attr:`_escbuf`.
    The length limits count the code units of :attr:`_escbuf`: a token of several bytes is appended whole while the
    buffer is below the limit, so the buffer can end up that many bytes longer.

    State, in the attributes the inheriting class sets up:

    - ``_within_escape``: an ESC was read and its sequence has not ended.
    - ``_parsestate``: the :class:`~urwid.ansi_parser.ParseState` of the sequence; :attr:`ParseState.ESCAPE` both
      right after an ESC and outside any sequence.
    - ``_escbuf``: the parameter and intermediate characters of an ESC or CSI sequence, or the body of a string,
      including a trailing ESC that may start its ST.
      A command string's body starts with the character that opened it.

    A hook that takes a whole sequence runs while that sequence is still the current one, so these attributes still
    describe it; the machine leaves the sequence after the hook returns.
    The hooks have no default, except :meth:`_vt_restart`: the inheriting class implements each one.
    """

    # No __slots__: the terminal canvas inherits it beside slotted canvas classes, whose layouts would conflict with
    # any slots of its own; the inheriting class holds the three attributes below.

    _within_escape: bool
    _parsestate: ParseState
    # Any rather than _TextT: Pyrefly does not follow a constrained type variable through updates of an attribute
    _escbuf: typing.Any
    # the class attributes the inheriting class sets, in its token type:
    #: an empty buffer, an ESC, and the first character of the Linux console's palette OSC
    _VT_EMPTY: typing.Any
    _VT_ESC: _TextT
    _VT_PALETTE_SET: _TextT
    #: a run of CSI parameter and intermediate characters, and a run of characters a string keeps as they are:
    #: anything but C0 controls, ESC and DEL, which a DCS string ignores
    _VT_CSI_RUN: re.Pattern[typing.Any]
    _VT_STRING_RUN: re.Pattern[typing.Any]

    @property
    def _vt_linux_palette(self) -> bool:
        """Return whether the Linux console's palette OSC is read: framed by its length and taken by a hook."""
        raise NotImplementedError

    def _vt_leave(self) -> None:
        """Drop the sequence being read and return to the ground state."""
        self._within_escape = False
        self._parsestate = _ESCAPE
        self._escbuf = self._VT_EMPTY

    def _vt_step(self, token: _TextT, code: int) -> None:
        """Feed one token with code point *code* through the machine.

        Flow, in order of the checks:

        .. code-block:: text

            CSI parameter  -> appended, or dropped past MAX_CSI_LENGTH
            DEL after ESC  -> ignored inside a string, so the ESC can still start ST
            OSC string     -> CAN/SUB aborts; a control is ignored, or executed after an ESC; else _vt_osc_char
            command string -> CAN/SUB aborts; a control is ignored, or executed after an ESC; ST ends it;
                              an ESC followed by anything else starts a new sequence; else the body grows,
                              and past MAX_OSC_LENGTH only its last character is kept
            C0 control/DEL -> executed, a sequence in progress continues
            CAN/SUB        -> the sequence is dropped
            ESC            -> drops a sequence in progress (_vt_interrupted) and starts a new one
            in a sequence  -> _vt_escape_char
            otherwise      -> printed
        """
        state = self._parsestate
        if state == _CSI and 0x20 <= code <= 0x3F:
            # a parameter or intermediate byte, ECMA-48 5.4, the commonest character inside a sequence; past the limit
            # the parameters are dropped, and the sequence is skipped by its length
            if len(self._escbuf) < MAX_CSI_LENGTH:
                self._escbuf += token
            return
        if code == _DEL and state in _STRING_STATES and self._escbuf[-1:] == self._VT_ESC:
            # DEL after an ESC inside a string is ignored, as in xterm, so a following backslash still ends the string
            return
        if state in _OSC_STATES:
            if code in _CANCEL_CODES:
                if state == _OSC:
                    self._vt_osc_unterminated(self._escbuf.removesuffix(self._VT_ESC))
                self._vt_leave()
            elif code not in _OSC_IGNORED_CODES:
                self._vt_osc_char(token, code)
            elif self._escbuf[-1:] == self._VT_ESC:
                # after an ESC the control character is executed and the ESC stays pending, so a following backslash
                # still ends the string
                self._vt_execute(token, code)
            return
        if state in _COMMAND_STRING_STATES:
            if code in _CANCEL_CODES:
                self._vt_leave()
            elif code not in _COMMAND_STRING_IGNORED_CODES:
                if self._escbuf[-1:] == self._VT_ESC and code != _BACKSLASH:
                    # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the
                    # string unapplied and starts a new escape sequence
                    self._vt_leave()
                    self._within_escape = True
                    self._vt_restart(token, code)
                elif self._escbuf[-1:] == self._VT_ESC:
                    self._vt_string_end(self._escbuf[:-1] if state == _COMMAND_STRING else None)
                    self._vt_leave()
                elif state == _COMMAND_STRING_OVERFLOW:
                    # only the last character is kept, which is enough to recognise ST
                    self._escbuf = self._VT_EMPTY + token
                elif len(self._escbuf) < MAX_OSC_LENGTH:
                    self._escbuf += token
                else:
                    self._parsestate = _COMMAND_STRING_OVERFLOW
                    self._escbuf = self._VT_EMPTY + token
            elif self._escbuf[-1:] == self._VT_ESC and code != _BEL:
                # after an ESC the control character is executed, as in an OSC string; BEL is no terminator here
                self._vt_execute(token, code)
            return
        if code in _EXECUTED_CODES:
            self._vt_execute(token, code)
            return
        if code in _CANCEL_CODES:
            self._vt_leave()
            return
        if code == _ESC:
            if self._within_escape:
                # as in a terminal, an ESC drops a sequence still being read and starts a new one
                self._vt_interrupted()
                self._vt_leave()
            self._within_escape = True
            return
        if self._within_escape:
            self._vt_escape_char(token, code)
            return
        self._vt_print(token, code)

    def _vt_append_run(self, text: _TextT, start: int) -> int:
        """Append the run of characters from *start* that the sequence being read keeps as they are, in one step.

        The result is the one :meth:`_vt_step` gives fed the same characters one by one, when each token is one code
        unit: a ``str`` character, or a byte in a single-byte encoding. A class whose tokens can be several bytes
        long steps them one by one instead.
        Only what needs no decision per character is appended: CSI parameters, and string bodies that cannot end in
        a palette OSC, up to the length limit.

        :returns: the index after the characters taken, *start* when none were.
        """
        state = self._parsestate
        buffer = self._escbuf
        if state == _CSI:
            pattern, limit = self._VT_CSI_RUN, MAX_CSI_LENGTH
        elif state == _COMMAND_STRING or (state == _OSC and buffer and buffer[:1] != self._VT_PALETTE_SET):
            if buffer[-1:] == self._VT_ESC:
                return start
            pattern, limit = self._VT_STRING_RUN, MAX_OSC_LENGTH
        else:
            return start
        match = pattern.match(text, start)
        if match is None:
            return start
        end: int = match.end()
        taken = min(end, start + max(limit - len(buffer), 0))
        if taken > start:
            self._escbuf = buffer + text[start:taken]
        # CSI parameters past the limit are dropped, while a string past it changes state at the next character
        return end if state == _CSI else taken

    def _vt_escape_char(self, token: _TextT, code: int) -> None:
        """Feed *token* to the ESC or CSI sequence being read."""
        state = self._parsestate
        if state == _CSI:
            # the parameter and intermediate bytes were collected in _vt_step, so this is the final byte
            self._vt_csi_dispatch(token, self._escbuf)
            self._vt_leave()
            return
        if state == _ESCAPE:
            if code == 0x5D:  # ESC ]
                self._escbuf = self._VT_EMPTY
                self._parsestate = _OSC
                return
            if code == 0x5B:  # ESC [
                self._escbuf = self._VT_EMPTY
                self._parsestate = _CSI  # pylint: disable=redefined-variable-type  # members of one enum
                return
            if code in _STRING_OPENER_CODES:
                # the opening character is kept, to tell a DCS from the others when the string ends
                self._vt_string_start(token)
                self._escbuf = self._VT_EMPTY + token
                self._parsestate = _COMMAND_STRING
                return
        if 0x20 <= code <= 0x2F:
            # an intermediate byte of an escape sequence (ECMA-35), such as the "(" of a G0 designation; past the limit
            # the intermediate bytes are dropped, and the sequence still ends at its final byte
            if state == _ESCAPE:
                self._escbuf = self._VT_EMPTY
                self._parsestate = _ESC_INTERMEDIATE
            if len(self._escbuf) < MAX_CSI_LENGTH:
                self._escbuf += token
            return
        self._vt_esc_dispatch(token, self._escbuf if state == _ESC_INTERMEDIATE else self._VT_EMPTY)
        self._vt_leave()

    def _vt_osc_char(self, token: _TextT, code: int) -> None:
        """Feed *token*, which is no ignored control character, to the OSC string being read."""
        buffer = self._escbuf
        if buffer[-1:] == self._VT_ESC and code != _BACKSLASH:
            # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the string
            # unapplied and starts a new escape sequence
            if self._parsestate == _OSC:
                self._vt_osc_unterminated(buffer[:-1])
            self._vt_leave()
            self._within_escape = True
            self._vt_restart(token, code)
            return
        if self._parsestate == _OSC_OVERFLOW:
            # only the last character is kept, which is enough to recognise either terminator
            if code == _BEL or (buffer == self._VT_ESC and code == _BACKSLASH):
                self._vt_leave()
            else:
                self._escbuf = self._VT_EMPTY + token
            return
        if code == _BEL or (buffer[-1:] == self._VT_ESC and code == _BACKSLASH):
            self._vt_osc_dispatch(buffer if code == _BEL else buffer[:-1], bel=code == _BEL)
            self._vt_leave()
            return
        if len(buffer) >= MAX_OSC_LENGTH:
            self._vt_osc_overflow(buffer)
            self._parsestate = _OSC_OVERFLOW
            self._escbuf = self._VT_EMPTY + token
            return
        if not buffer and code == _PALETTE_RESET and self._vt_linux_palette:
            self._vt_osc_palette(self._VT_EMPTY + token)
            self._vt_leave()
            return
        self._escbuf = buffer = buffer + token
        # an ESC is no digit: the next character decides whether it starts ST or a new sequence
        if (
            code != _ESC
            and len(buffer) == _PALETTE_SET_LENGTH
            and buffer[:1] == self._VT_PALETTE_SET
            and self._vt_linux_palette
        ):
            # the Linux console's palette set, ESC ] P n rr gg bb, ends with its 7th hex digit
            self._vt_osc_palette(buffer)
            self._vt_leave()

    # -- hooks the inheriting class implements -----------------------------------------------------------------------

    def _vt_print(self, token: _TextT, code: int) -> None:
        """Take a token outside any sequence that is no control character."""
        raise NotImplementedError

    def _vt_execute(self, token: _TextT, code: int) -> None:
        """Take a C0 control character or DEL, other than ESC, CAN and SUB, wherever it is executed."""
        raise NotImplementedError

    def _vt_esc_dispatch(self, final: _TextT, intermediates: _TextT) -> None:
        """Take the final character of an ESC sequence, with its intermediate characters."""
        raise NotImplementedError

    def _vt_csi_dispatch(self, final: _TextT, parameters: _TextT) -> None:
        """Take the final character of a CSI sequence, with its parameter and intermediate characters.

        *parameters* holds at most :data:`~urwid.ansi_parser.MAX_CSI_LENGTH` characters, and that many when the
        sequence was longer.
        """
        raise NotImplementedError

    def _vt_osc_dispatch(self, body: _TextT, *, bel: bool) -> None:
        """Take the body of an OSC string ended by BEL (*bel*) or ST, without its framing."""
        raise NotImplementedError

    def _vt_osc_palette(self, body: _TextT) -> None:
        """Take a Linux console palette OSC: ``R``, or ``P`` with its seven hex digits."""
        raise NotImplementedError

    def _vt_osc_overflow(self, body: _TextT) -> None:
        """Take the body of an OSC string that reached :data:`~urwid.ansi_parser.MAX_OSC_LENGTH` code units.

        The rest of it, up to its terminator, is discarded.
        """
        raise NotImplementedError

    def _vt_osc_unterminated(self, body: _TextT) -> None:
        """Take the body of an OSC string that CAN, SUB or an ESC not starting ST dropped."""
        raise NotImplementedError

    def _vt_restart(self, token: _TextT, code: int) -> None:
        """Feed *token* again, after an ESC that does not start ST ended a string and started a new sequence.

        The inheriting class may route it through its own per-character processing, as it would a token it reads.
        """
        self._vt_step(token, code)

    def _vt_interrupted(self) -> None:
        """Take note of an ESC that drops the ESC or CSI sequence still being read, before the machine drops it."""
        raise NotImplementedError

    def _vt_string_start(self, opener: _TextT) -> None:
        """Take the character after ESC that opens a DCS, SOS, PM or APC string."""
        raise NotImplementedError

    def _vt_string_end(self, body: _TextT | None) -> None:
        """Take a DCS, SOS, PM or APC string ended by ST, starting with the character that opened it.

        *body* is None when the string reached :data:`~urwid.ansi_parser.MAX_OSC_LENGTH` code units.
        """
        raise NotImplementedError
