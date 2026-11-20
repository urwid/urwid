# Urwid standalone ANSI/VT100 escape-sequence line parser
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

"""The incremental ANSI parser and the functions that run it over a whole text."""

from __future__ import annotations

import logging
import re
import types
import typing

from urwid.ansi_parser._grammar import (
    _CANCEL,
    _STRING_STATES,
    MAX_CSI_LENGTH,
    MAX_OSC_LENGTH,
    ParseState,
    _csi_parameters,
)
from urwid.ansi_parser._resolve import attrspec_with_hyperlink, led_state, resolve_osc_hyperlink, resolve_osc_title
from urwid.ansi_parser._results import _ASCII_SET, CharsetState, ParsedLine, SkippedOp
from urwid.ansi_parser._vt_parser import _VTParser
from urwid.display._sgr import parse_sgr_parameters, sgi_params_to_attrspec
from urwid.display.escape import _C0_CONTROLS, ALT_DEC_SPECIAL_CHARS, BEL, DEC_SPECIAL_CHARS, DEC_TAG, ESC, SI, SO
from urwid.util import rle_append_modify

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from urwid.display import AttrSpec


# named after the package, which is where logging configurations and the tests find it
LOGGER = logging.getLogger("urwid.ansi_parser")


#: CSI final bytes that move the cursor vertically -- meaningless outside a
#: two-dimensional screen buffer, so the whole operation is stripped and
#: logged rather than reinterpreted.
_VERTICAL_MOVE_CSI = frozenset("ABEFdHf")

#: CSI final bytes that mutate terminal-wide state (modes, scroll regions,
#: erase, insert/delete, device queries, tabstops, ...) -- again meaningless
#: for a single, canvas-less line of text.
_TERMINAL_SETTING_CSI = frozenset("hlrJKsu@LMPXcng")

#: Characters drawn in place of their ASCII counterparts while the DEC Special Graphics character set is shifted in.
_DEC_SPECIAL_GRAPHICS: typing.Final = str.maketrans(ALT_DEC_SPECIAL_CHARS, DEC_SPECIAL_CHARS)

#: fbterm's ``CSI 1;n }`` and ``CSI 2;n }``: the SGR parameters selecting 256-color palette index n as the
#: foreground or the background.
_FBTERM_COLOR_SGR: typing.Final = types.MappingProxyType({1: 38, 2: 48})

#: C0 control characters and DEL a terminal executes outside an OSC string, also inside another escape sequence, which
#: then continues; ESC, CAN, SUB and the line ends are handled apart. Importable from this package since 5.1.3.
_INLINE_CONTROLS = frozenset(map(chr, (*_C0_CONTROLS, 0x7F))) - {ESC, *_CANCEL, "\r", "\n"}

#: A run of characters that are no control characters, which feed() writes in one call outside any sequence.
_TEXT_RUN: typing.Final = re.compile("[^\x00-\x1f\x7f-\x9f]+")

#: Line-end byte pairs that collapse into a single structural split point.
_LINE_END_PAIR: dict[str, str] = {"\r": "\n", "\n": "\r"}

#: The furthest a relative cursor move advances, and the furthest 1-based row or column an absolute move reaches.
#: The input is untrusted, and a few bytes such as ``CSI 300000000 C`` would otherwise pad the grid with that many
#: cells. 1024 exceeds the width and height of practical terminals, and caps what one movement sequence adds to the
#: grid at 1024 cells.
_MAX_CURSOR_POSITION = 1024


#: The most entries a ``skipped`` list holds, covering one 64 KiB raw display read of 2-byte sequences.
_MAX_SKIPPED = 65536

#: Padding cells a parser may insert regardless of input length, one full 1024 x 1024 screen.
_PADDING_BUDGET = _MAX_CURSOR_POSITION * _MAX_CURSOR_POSITION

#: Padding cells each fed character adds to the budget, as many as a tab writes.
_PADDING_PER_CHARACTER = 8

#: Padding cells an empty row inserted by a vertical move costs, about what the row allocates.
_PADDING_PER_ROW = 8


class AnsiParser(_VTParser[str]):
    r"""Incremental ANSI parser that resolves escape sequences against a 2-D cell grid, in one of two modes.

    Feed text in with :meth:`feed` -- any number of times, e.g. as chunks arrive from a subprocess -- and call
    :meth:`finalize` once to retrieve the result. :meth:`finalize` is a one-shot, terminal operation: construct a
    fresh :class:`AnsiParser` per logical "session" of feeding.

    Internally, a :class:`AnsiParser` always maintains a two-dimensional grid of rows (one cell buffer per screen
    row) plus a cursor (``row``, ``col``). The two constructor modes below share the *overwhelming majority* of
    their behaviour -- printable characters, horizontal cursor movement (``CSI n C/D/G``), backspace, tab, SGR
    colour/attribute handling (``CSI ... m``, and fbterm's ``CSI 1;n }``/``CSI 2;n }`` colors), DEC Special Graphics
    selected with ``ESC ( 0``/``ESC ) 0`` and SI/SO, BEL, OSC window-title recognition, OSC 8 hyperlinks (carried in
    :attr:`AttrSpec.hyperlink <urwid.AttrSpec.hyperlink>` of the written text), keyboard-LED requests
    (``CSI n q``) and terminal-wide setting sequences (stripped and logged, see :class:`SkippedOp`) are interpreted
    identically regardless of mode. They differ only in how a **line end** and **vertical cursor movement** are
    treated, and in whether the side channels (``bel``, ``title``, ``leds``, ``skipped``) are reset per line or
    aggregated over the whole input:

    * ``one_line=True``: a line-end sequence (``\n``, ``\r``, ``\r\n`` or ``\n\r``, the latter two pairs
      collapsing into a single event; VT and FF too, see below) is a **structural split point**, not discarded
      data -- the moment one is seen, the current row is completed into a :class:`ParsedLine` and pushed onto an
      internal completed-lines queue, and a fresh row is started for what follows, carrying the SGR/colour state
      (:attr:`ParsedLine.last_attr`) forward but resetting the per-line side channels. Vertical cursor movement
      (``CSI n A/B/E/F/d`` and ``CSI r;c H``/``f``) is meaningless outside a single line, so it is stripped and
      logged as a :class:`SkippedOp` rather than reinterpreted. An escape sequence in progress at a line end
      continues on the next line, as in a terminal, so the attributes it sets apply there.
      A line end inside an OSC string is the exception, as described below.
    * ``one_line=False`` (the default): a full newline (``\n``, or a collapsed ``\r\n``/``\n\r`` pair) genuinely
      moves to a fresh row, resetting the column, while everything keeps accumulating in the same persistent grid
      -- nothing is split off. A **bare** ``\r`` (not part of a ``\r\n``/``\n\r`` pair) is carriage-return-only:
      it resets the column without changing row, letting progress-bar-style in-place redraw sequences
      (``"progress: 10%\rprogress: 20%"``) resolve correctly onto a single row, mirroring real terminal behaviour.
      Vertical cursor movement genuinely repositions the cursor within the grid instead of being stripped. The side
      channels are aggregated over the *entire* input rather than reset per row: ``bel`` is the total BEL count,
      ``title``/``leds`` are the last value seen anywhere, and ``skipped`` lists the :class:`SkippedOp`
      entries in encounter order.

    C0 control characters and DEL are executed as in a terminal, also inside an escape sequence, which then
    continues: BEL is counted, tab and backspace move the cursor, VT and FF are line feeds (completing the line in
    ``one_line`` mode, else moving one row down in the same column), CAN and SUB abort the sequence, and the others
    are ignored, so none of them is part of the resolved text. An ESC outside an OSC string drops a sequence still
    being read, recorded as a :class:`SkippedOp`, and starts a new one. A C1 control character (U+0080 to U+009F)
    in the text is dropped and takes no column, as xterm does with C1 controls in UTF-8 text.

    SGR bold stays a setting of its own and does not brighten the foreground: ``CSI 1;31 m`` is
    ``'dark red,bold'``, and a display draws it in a bright color where the terminal does so for bold text.
    So the escapes of a terminal that shows bright colors as bold, or bright backgrounds as blink (the Linux
    console), come back as bold or blink with the basic color. A ``CSI 38;5;n m`` index is read in the 256-color
    palette, also when it was written for an 88-color terminal. G1 starts as DEC Special Graphics, as on the Linux
    console, so the SO/SI-wrapped line drawing of the raw display is drawn without a designation in the input.
    A character set other than DEC Special Graphics and US ASCII is drawn as ASCII, and its designation is recorded
    as a :class:`SkippedOp`. A terminal reset (``ESC c``) designates US ASCII to G0 and G1 and selects G0; it leaves
    the SGR state as it is and is recorded as a :class:`SkippedOp`.

    Inside an OSC string, in both modes, a control character in :data:`OSC_IGNORED_CONTROLS`, line ends included,
    is ignored as in a terminal: it is neither executed nor part of the string, and a line end there splits no line.
    Right after an ESC inside the string, a control character is executed instead, and the ESC stays pending, so a
    following backslash still ends the string; DEL there is ignored, as in xterm, and the ESC stays pending too.
    An OSC string left unterminated hides the rest of the input.
    A DCS, SOS, PM or APC string is discarded up to its ST in the same way, and BEL inside it is ignored as well.
    An escape sequence with intermediate bytes, such as ``ESC SP G``, is read up to its final byte.

    Deliberately out of scope in both modes (stripped and logged as :class:`SkippedOp` with
    ``kind="terminal-setting"`` or ``kind="unknown"``): erase (``CSI J``/``K``), scroll regions, save/restore
    cursor, mode toggles, insert/delete, device queries, tabstops, and the non-CSI vertical-movement escapes
    (``ESC D``/``M``/``E``) -- a genuine two-dimensional buffer would technically allow implementing erase and
    save/restore cursor, but that is a candidate follow-up, kept out of scope here. Text sizing (OSC 66) is not
    interpreted either: it is stripped together with the text it carries.

    The padding inserted to reach a moved cursor -- blank cells before a written character and empty rows below the
    last one -- is limited to ``1024 * 1024 + 8 * n`` cells over the parser's lifetime, ``n`` being the number of
    characters parsed so far, and an empty row counts as 8 cells.
    The limit is therefore the same however the input is split into :meth:`feed` calls.
    Once the limit is reached, a character is written at the end of its row instead,
    a vertical move past the last row stays on the last row,
    and each such cut is recorded as a :class:`SkippedOp` with ``kind="unknown"``.

    :meth:`finalize` returns a uniform ``tuple[ParsedLine, ...]`` in both modes: in ``one_line=True`` mode, every
    line completed since construction (queue plus a final flush of whatever remains, possibly empty or
    unterminated); in ``one_line=False`` mode, always exactly one :class:`ParsedLine` -- built from the whole grid,
    rows joined with ``"\n"`` -- wrapped in a 1-tuple.

    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from previously
        parsed text, or the :class:`ParsedLine` parsed before, whose attribute and character sets both carry over.
    :param one_line: if true, treat line ends as structural split points that yield multiple :class:`ParsedLine`
        results; if false (the default), resolve the whole input into a single multi-row :class:`ParsedLine`.

    >>> parser = AnsiParser(one_line=True)
    >>> parser.feed("hello\nworld")
    >>> [line.text for line in parser.finalize()]
    ['hello', 'world']

    >>> parser = AnsiParser()
    >>> parser.feed("hello\nworld")
    >>> parser.finalize()[0].text
    'hello\nworld'
    """

    _VT_EMPTY = ""
    _VT_ESC = ESC
    _VT_PALETTE_SET = "P"
    _VT_CSI_RUN = re.compile("[ -?]+")
    _VT_STRING_RUN = re.compile("[^\x00-\x1f\x1b\x7f]+")

    def __init__(self, previous_attr: AttrSpec | ParsedLine | None = None, *, one_line: bool = False) -> None:
        """Create a parser, as described in the class docstring."""
        charsets = CharsetState()
        if isinstance(previous_attr, ParsedLine):
            charsets = previous_attr.last_charsets
            previous_attr = previous_attr.last_attr
        self._one_line = one_line
        self._attrspec: AttrSpec | None = previous_attr

        # one cell buffer per screen row, plus a 2-D cursor -- in one_line
        # mode there is conceptually only ever one row: it is snapshotted
        # and reset at each structural split, see _complete_line()
        self._rows: list[list[tuple[str, Hashable | None]]] = [[]]
        self._row = 0
        self._col = 0

        # padding cells still allowed, and the last cursor move a cut padding is recorded against
        self._padding_budget = _PADDING_BUDGET
        self._last_move = ""

        # side channels -- reset per completed line in one_line mode (see
        # _complete_line()), aggregated over the entire input otherwise
        self._bel_count = 0
        self._title: str | None = None
        self._leds: str | None = None
        self._skipped: list[SkippedOp] = []

        # completed-lines queue, used only in one_line mode
        self._completed: list[ParsedLine] = []

        # escape-framing state; this parser discards DCS, SOS, PM and APC strings
        self._within_escape = False
        self._parsestate: ParseState = ParseState.ESCAPE
        self._escbuf = ""

        # the final bytes designating G0 and G1, and the one SI/SO selected; G1 starts as DEC Special Graphics,
        # as in urwid.vterm and the Linux console
        self._charsets = [charsets.g0, charsets.g1]
        self._active_charset: typing.Literal[0, 1] = charsets.selected

        # a line-end byte seen at the very end of the previous feed() call,
        # kept around in case the next feed() call opens with its pairing
        # complement (completing a \r\n / \n\r pair split across chunks)
        self._pending_line_end: str | None = None

    def feed(self, text: str) -> None:
        """Feed another chunk of decoded text into the parser.

        Chunks need not be aligned on line, row or escape-sequence boundaries; state (including a line end split
        across two calls, or an escape sequence split across two calls) is carried over correctly.

        :param text: the next chunk of decoded text to parse.
        """
        if not text:
            return

        # the padding budget grows by each character as it is parsed, see the class docstring
        if self._pending_line_end is not None:
            pending = self._pending_line_end
            self._pending_line_end = None
            if text[:1] == _LINE_END_PAIR.get(pending):
                self._padding_budget += _PADDING_PER_CHARACTER
                text = text[1:]
                if not self._one_line and pending == "\r":
                    # \r\n split across a feed() call boundary: the bare CR
                    # half was already applied (column reset) when it was
                    # first seen, so only the row advance is still owed
                    self._newline()
                # in one_line mode the split point was already handled in
                # full when the first half was seen; a pending "\n" in
                # screen mode needs no further action either, for the same
                # reason

        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if not self._within_escape:
                # the character test first: a regex match costs more, and most characters it rejects are ESC
                if (ch >= "\xa0" or " " <= ch < "\x7f") and (run := _TEXT_RUN.match(text, i)) is not None:
                    self._write_run(run[0])
                    i = run.end()
                    continue
            elif ch >= " " and ch != ESC and (end := self._vt_append_run(text, i)) > i:
                self._padding_budget += _PADDING_PER_CHARACTER * (end - i)
                i = end
                continue
            self._padding_budget += _PADDING_PER_CHARACTER
            if ch in _LINE_END_PAIR:
                if self._parsestate in _STRING_STATES and self._escbuf[-1:] != ESC:
                    # a line end inside a command string is ignored, as other control characters there are
                    i += 1
                    continue
                if self._one_line:
                    # an escape sequence in progress continues on the next line, as in a terminal
                    self._complete_line()
                    if i + 1 < n and text[i + 1] == _LINE_END_PAIR[ch]:
                        self._padding_budget += _PADDING_PER_CHARACTER
                        i += 2
                    else:
                        if i + 1 == n:
                            self._pending_line_end = ch
                        i += 1
                    continue
                if i + 1 < n and text[i + 1] == _LINE_END_PAIR[ch]:
                    self._padding_budget += _PADDING_PER_CHARACTER
                    self._newline()
                    i += 2
                    continue
                if ch == "\n":
                    self._newline()
                else:
                    self._col = 0
                if i + 1 == n:
                    self._pending_line_end = ch
                i += 1
                continue
            self._vt_step(ch, ord(ch))
            i += 1

    def finalize(self) -> tuple[ParsedLine, ...]:
        r"""Retrieve the parsed result, in a uniform ``tuple[ParsedLine, ...]`` shape regardless of mode.

        In ``one_line=True`` mode, whatever remains in the current (possibly empty, possibly unterminated) row is
        flushed as one final :class:`ParsedLine`, and every line completed since construction is returned, in
        order. In ``one_line=False`` mode, the whole accumulated grid is resolved into a single :class:`ParsedLine`
        (its ``text`` joining every resolved row with ``"\n"``) and returned as a 1-tuple.

        This is a terminal operation: construct a new :class:`AnsiParser` to parse a fresh "session" of input.
        An OSC string the input leaves unterminated hides all text after it, as in a terminal; unless it was already
        recorded as over-long, it is recorded as a :class:`SkippedOp` of the last line.

        :returns: a uniform ``tuple[ParsedLine, ...]``, shaped as described above.
        """
        if self._parsestate == ParseState.OSC:
            self._skip("unknown", f"{ESC}]{self._escbuf.removesuffix(ESC)}", "unterminated OSC string")
        if self._one_line:
            self._complete_line()
            return tuple(self._completed)

        text_parts: list[str] = []
        attrib: list[tuple[Hashable, int]] = []
        for index, row in enumerate(self._rows):
            if index:
                text_parts.append("\n")
                rle_append_modify(attrib, (None, 1))
            text_parts.append("".join(char for char, _attr in row))
            for _char, attr in row:
                rle_append_modify(attrib, (attr, 1))

        parsed = ParsedLine(
            text="".join(text_parts),
            attrib=attrib,
            last_attr=self._attrspec,
            bel=self._bel_count,
            title=self._title,
            leds=self._leds,
            skipped=self._skipped.copy(),
            last_charsets=self._charset_state(),
        )
        return (parsed,)

    # -- internal: line/row completion and cursor management -------------

    def _complete_line(self) -> None:
        row = self._rows[0]
        text = "".join(char for char, _attr in row)
        attrib: list[tuple[Hashable, int]] = []
        for _char, attr in row:
            rle_append_modify(attrib, (attr, 1))

        self._completed.append(
            ParsedLine(
                text=text,
                attrib=attrib,
                last_attr=self._attrspec,
                bel=self._bel_count,
                title=self._title,
                leds=self._leds,
                skipped=self._skipped,
                last_charsets=self._charset_state(),
            )
        )

        self._rows = [[]]
        self._col = 0
        self._bel_count = 0
        self._title = None
        self._leds = None
        self._skipped = []

    def _charset_state(self) -> CharsetState:
        return CharsetState(self._charsets[0], self._charsets[1], self._active_charset)

    def _ensure_row(self, row: int) -> None:
        while len(self._rows) <= row:
            self._rows.append([])

    def _move_to_row(self, row: int, raw: str) -> None:
        """Move the cursor to ``row``, inserting the missing empty rows up to it within the padding budget.

        Without enough budget the cursor moves to the last existing row instead, and ``raw`` is recorded as skipped.
        """
        cost = (row + 1 - len(self._rows)) * _PADDING_PER_ROW
        if cost > self._padding_budget:
            self._skip("unknown", raw, "padding limit reached, cursor kept on the last row")
            row = min(row, len(self._rows) - 1)
        elif cost > 0:
            self._padding_budget -= cost
            self._ensure_row(row)
        self._row = row

    def _newline(self) -> None:
        self._row += 1
        self._ensure_row(self._row)
        self._col = 0

    # -- internal: the hooks of the state machine in urwid.ansi_parser._vt_parser -----------------------------------

    def _vt_print(self, token: str, code: int) -> None:
        """Write a character outside any sequence in the current character set."""
        if 0x80 <= code < 0xA0:
            # a C1 control in text is neither run nor drawn, as in xterm and urwid.vterm with UTF-8 input
            return
        if self._charsets[self._active_charset] == DEC_TAG:
            token = token.translate(_DEC_SPECIAL_GRAPHICS)
        self._write_char(token, self._attrspec)

    def _vt_execute(self, token: str, code: int) -> None:
        """Execute a control character, see :meth:`_execute_control`."""
        self._execute_control(token)

    def _vt_interrupted(self) -> None:
        """Record the sequence an ESC drops."""
        reason = "escape sequence interrupted by ESC"
        if len(self._escbuf) >= MAX_CSI_LENGTH:
            reason += f", its CSI parameters of {MAX_CSI_LENGTH} characters or more truncated"
        self._skip("unknown", f"{ESC}{'[' if self._parsestate == ParseState.CSI else ''}{self._escbuf}", reason)

    def _vt_esc_dispatch(self, final: str, intermediates: str) -> None:
        """Apply an ESC sequence, or record it as skipped."""
        if intermediates or final in "cDEHMZ78>=":
            self._dispatch_noncsi(final, intermediates)
        else:
            self._skip("unknown", f"{ESC}{final}", f"unrecognised escape sequence ESC {final!r}")

    def _vt_string_start(self, opener: str) -> None:
        """Record a DCS, SOS, PM or APC string, which this parser discards."""
        self._skip("unknown", f"{ESC}{opener}", "DCS, SOS, PM and APC strings are not supported, discarded")

    def _vt_string_end(self, body: str | None) -> None:
        """Discard a DCS, SOS, PM or APC string, recorded when it started."""

    def _execute_control(self, ch: str) -> None:
        """Execute C0 control character or DEL *ch* as a terminal does, leaving any escape sequence in progress.

        BEL is counted, tab and backspace move the cursor, SO and SI select G1 and G0, and VT and FF are line feeds:
        in one_line mode they complete the line, otherwise they move the cursor one row down, keeping its column.
        The others are ignored.
        """
        if ch == BEL:
            self._bel_count += 1
        elif ch == SO:
            self._active_charset = 1
        elif ch == SI:
            self._active_charset = 0
        elif ch == "\t":
            self._handle_tab()
        elif ch == "\b":
            self._col = max(0, self._col - 1)
        elif ch in {"\v", "\f"}:
            if self._one_line:
                self._complete_line()
            else:
                self._last_move = ch
                self._move_to_row(self._row + 1, ch)

    def _handle_tab(self, tabstop: int = 8) -> None:
        target = ((self._col // tabstop) + 1) * tabstop
        while self._col < target:
            self._write_char(" ", self._attrspec)

    def _write_run(self, run: str) -> None:
        """Write *run*, characters that are no control characters, as :meth:`_vt_print` writes each of them."""
        if self._charsets[self._active_charset] == DEC_TAG:
            run = run.translate(_DEC_SPECIAL_GRAPHICS)
        # only the first character can pad up to the cursor, so the rest get their padding credit after it
        self._padding_budget += _PADDING_PER_CHARACTER
        attr = self._attrspec
        self._write_char(run[0], attr)
        if rest := len(run) - 1:
            self._padding_budget += _PADDING_PER_CHARACTER * rest
            col = self._col
            self._rows[self._row][col : col + rest] = [(char, attr) for char in run[1:]]
            self._col = col + rest

    def _write_char(self, ch: str, attr: Hashable | None) -> None:
        row = self._rows[self._row]
        if self._col < len(row):
            row[self._col] = (ch, attr)
        elif self._col == len(row):
            row.append((ch, attr))
        else:
            gap = self._col - len(row)
            if gap > self._padding_budget:
                self._skip("unknown", self._last_move, "padding limit reached, written at the end of the row")
                self._col = len(row)
            else:
                self._padding_budget -= gap
                row.extend([(" ", None)] * gap)
            row.append((ch, attr))
        self._col += 1

    # -- internal: escape/CSI/OSC framing --------------------------------

    def _skip(self, kind: str, raw: str, reason: str) -> None:
        """Record a stripped sequence and log it at debug level.

        Entries past the first :data:`_MAX_SKIPPED` are not recorded.
        Untrusted input can repeat a sequence without limit.
        A warning would reach stderr, over the UI, through Python's last-resort handler.
        """
        if len(self._skipped) < _MAX_SKIPPED:
            self._skipped.append(SkippedOp(kind=kind, raw=raw, reason=reason))
        LOGGER.debug("%s: %r", reason, raw)

    def _vt_csi_dispatch(self, final: str, parameters: str) -> None:
        """Apply a CSI sequence, or record it as skipped."""
        raw = f"{ESC}[{parameters}{final}"
        if len(parameters) >= MAX_CSI_LENGTH:
            self._skip("unknown", raw, f"CSI parameters of {MAX_CSI_LENGTH} characters or more, truncated")
            return

        qmark = parameters.startswith("?")
        body = parameters[1:] if qmark else parameters
        if final == "m" and not qmark and not body.strip("0123456789;:"):
            # a color the text leaves unset shows the background or foreground of the widget around it, and bold
            # stays bold: the display brightens it again where the terminal draws bold text in bright colors
            self._attrspec = sgi_params_to_attrspec(
                parse_sgr_parameters(body),
                self._attrspec,
                unset_color="inherit",
                bright_is_bold=False,
            )
            return
        if (parsed := _csi_parameters(body)) is None:
            self._skip("unknown", raw, "CSI sub-parameters, private markers and intermediate bytes are not supported")
            return
        params = parsed if body else []

        if (
            final == "}"
            and not qmark
            and len(params) == 2
            and (extended_color := _FBTERM_COLOR_SGR.get(params[0] or 0)) is not None
        ):
            color = params[1] or 0
            if color > 255:
                self._skip("unknown", raw, "fbterm color index out of range")
            else:
                self._attrspec = sgi_params_to_attrspec(
                    [extended_color, 5, color],
                    self._attrspec,
                    unset_color="inherit",
                    bright_is_bold=False,
                )
        elif final == "}":
            self._skip("terminal-setting", raw, "fbterm setting other than a color")
        elif final == "C":
            n = params[0] if params and params[0] else 1
            self._col += min(n, _MAX_CURSOR_POSITION)
            self._last_move = raw
        elif final == "D":
            n = params[0] if params and params[0] else 1
            self._col = max(0, self._col - n)
        elif final == "G":
            n = params[0] if params and params[0] else 1
            self._col = min(n, _MAX_CURSOR_POSITION) - 1
            self._last_move = raw
        elif final == "q":
            mode = params[0] if params and params[0] else 0
            self._leds = led_state(mode)
        elif final in _VERTICAL_MOVE_CSI:
            self._dispatch_vertical_move_csi(final, params, raw)
        elif final in _TERMINAL_SETTING_CSI:
            self._skip("terminal-setting", raw, f"CSI {final!r} terminal-wide setting is out of scope for this pass")
        else:
            self._skip("unknown", raw, f"unrecognised CSI final byte {final!r}")

    def _dispatch_vertical_move_csi(self, final: str, params: list[int | None], raw: str) -> None:
        if self._one_line:
            # meaningless outside a full two-dimensional screen buffer, so
            # the whole operation is stripped and logged rather than
            # reinterpreted
            self._skip("vertical-move", raw, f"CSI {final!r} vertical cursor movement is meaningless for a single line")
            return
        self._last_move = raw

        # these genuinely reposition the cursor within the grid
        if final == "A":
            n = params[0] if params and params[0] else 1
            self._row = max(0, self._row - n)
        elif final == "B":
            n = params[0] if params and params[0] else 1
            self._move_to_row(self._row + min(n, _MAX_CURSOR_POSITION), raw)
        elif final == "E":
            n = params[0] if params and params[0] else 1
            self._move_to_row(self._row + min(n, _MAX_CURSOR_POSITION), raw)
            self._col = 0
        elif final == "F":
            n = params[0] if params and params[0] else 1
            self._row = max(0, self._row - n)
            self._col = 0
        elif final == "d":
            n = params[0] if params and params[0] else 1
            self._move_to_row(min(n, _MAX_CURSOR_POSITION) - 1, raw)
        elif final in ("H", "f"):
            r = params[0] if params and params[0] else 1
            c = params[1] if len(params) > 1 and params[1] else 1
            self._move_to_row(min(r, _MAX_CURSOR_POSITION) - 1, raw)
            self._col = min(c, _MAX_CURSOR_POSITION) - 1

    def _dispatch_noncsi(self, ch: str, mod: str) -> None:
        raw = f"{ESC}{mod}{ch}"
        if mod == "#" and ch == "8":
            self._skip("terminal-setting", raw, "DECALN screen alignment test")
        elif mod == "#":
            # the single-character sequences below take no intermediate byte
            self._skip("unknown", raw, f"unrecognised escape sequence {raw!r}")
        elif mod == "%":
            self._skip("terminal-setting", raw, "character set selection")
        elif mod in ("(", ")"):
            self._charsets[0 if mod == "(" else 1] = ch
            if ch not in {_ASCII_SET, DEC_TAG}:
                self._skip("terminal-setting", raw, "unsupported character set designation, drawn as ASCII")
        elif mod:
            # another intermediate byte: its final byte is no single-character sequence of its own
            self._skip("unknown", raw, f"unrecognised escape sequence {raw!r}")
        elif ch == "M":
            self._skip("vertical-move", raw, "reverse line feed")
        elif ch == "D":
            self._skip("vertical-move", raw, "line feed")
        elif ch == "E":
            self._skip("vertical-move", raw, "newline")
        elif ch == "H":
            self._skip("terminal-setting", raw, "set tabstop")
        elif ch == "c":
            self._charsets = [_ASCII_SET, _ASCII_SET]
            self._active_charset = 0
            self._skip("terminal-setting", raw, "terminal reset, applied to the character sets only")
        elif ch in ("7", "8"):
            self._skip("terminal-setting", raw, "save/restore cursor")
        elif ch in (">", "=", "Z"):
            self._skip("terminal-setting", raw, "keypad mode / device attributes")
        else:
            self._skip("unknown", raw, f"unrecognised escape sequence {raw!r}")

    def _vt_osc_dispatch(self, body: str) -> None:
        """Apply an OSC window title or hyperlink, or record another OSC string as skipped."""
        raw = f"{ESC}]{body}"
        title = resolve_osc_title(body)
        if title is not None:
            self._title = title
            return
        try:
            link = resolve_osc_hyperlink(body)
        except ValueError:
            # the text after it must not keep pointing at the previous link
            self._attrspec = attrspec_with_hyperlink(self._attrspec, None, unset_color="inherit")
            self._skip("unknown", raw, "invalid OSC 8 hyperlink, current link ended")
            return
        if link is not None:
            self._attrspec = attrspec_with_hyperlink(self._attrspec, link, unset_color="inherit")
        else:
            self._skip("terminal-setting", raw, "unrecognised OSC prefix")

    def _vt_osc_palette(self, body: str) -> None:
        """Record a Linux console palette OSC as skipped."""
        self._skip("terminal-setting", f"{ESC}]{body}", "OSC palette reset" if body == "R" else "OSC palette set")

    def _vt_osc_overflow(self, body: str) -> None:
        """Record an over-long OSC string as skipped; an over-long OSC 8 ends the current link."""
        if body.lstrip("0").startswith("8;"):
            # an over-long OSC 8 is refused like any other invalid one, ending the current link
            self._attrspec = attrspec_with_hyperlink(self._attrspec, None, unset_color="inherit")
        self._skip("unknown", f"{ESC}]{body}", f"OSC string of {MAX_OSC_LENGTH} characters or more, truncated")

    def _vt_osc_unterminated(self, body: str) -> None:
        """Record an OSC string CAN, SUB or another sequence dropped."""
        self._skip("unknown", f"{ESC}]{body}", "unterminated OSC string")


def parse_ansi_line(text: str, previous_attr: AttrSpec | ParsedLine | None = None) -> tuple[ParsedLine, ...]:
    r"""Feed ``text`` through a fresh :class:`AnsiParser` (``one_line=True``) and return its finalised result.

    Returns one :class:`ParsedLine` per line found in ``text`` (split on ``\n``/``\r``/``\r\n``/``\n\r``, VT
    and FF), plus a trailing entry for a final unterminated fragment, if any -- never fewer than one element, even for
    empty input. Line ends are structural split points, not stripped content, except inside an OSC string, where
    they are ignored; other control characters and escape sequences are not part of the text, see
    :class:`AnsiParser`.

    :param text: the text to parse.
    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from a
        previously parsed line, or that :class:`ParsedLine` itself, to carry its character sets over as well.
    :returns: every :class:`ParsedLine` found in ``text``, in order.

    >>> [line.text for line in parse_ansi_line("one\ntwo\nthree")]
    ['one', 'two', 'three']
    >>> [line.text for line in parse_ansi_line("")]
    ['']
    >>> [line.text for line in parse_ansi_line("a\nb")]
    ['a', 'b']
    """
    parser = AnsiParser(previous_attr, one_line=True)
    parser.feed(text)
    return parser.finalize()


def parse_ansi_text(text: str, previous_attr: AttrSpec | ParsedLine | None = None) -> ParsedLine:
    r"""Feed ``text`` through a fresh :class:`AnsiParser` (``one_line=False``) and return its sole resolved line.

    Unlike :func:`parse_ansi_line`, vertical cursor movement and newlines are resolved into real multi-row output
    rather than stripped/split: the returned single :class:`ParsedLine`'s ``text`` joins every resolved row with
    ``"\n"``.

    :param text: the text to parse.
    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from previously
        parsed text, or the :class:`ParsedLine` of that text, to carry its character sets over as well.
    :returns: a single :class:`ParsedLine` representing the whole resolved block.

    >>> parse_ansi_text("one\ntwo\nthree").text
    'one\ntwo\nthree'
    >>> parse_ansi_text("").text
    ''
    >>> parse_ansi_text("progress: 10%\rprogress: 20%").text
    'progress: 20%'
    """
    parser = AnsiParser(previous_attr, one_line=False)
    parser.feed(text)
    return parser.finalize()[0]
