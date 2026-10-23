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
"""Standalone ANSI/VT100 escape-sequence parsing, decoupled from any canvas.

This module extracts the platform-independent portion of the escape-sequence
grammar historically embedded inside :mod:`urwid.vterm`'s ``TermCanvas`` --
SGR colour/attribute interpretation, horizontal cursor movement, BEL, OSC
title, OSC 8 hyperlink, DEC Special Graphics and keyboard-LED recognition -- into a form that can be used to
interpret a single string (or a stream of chunks) of ANSI-coloured text
without instantiating a pty-backed :class:`~urwid.Terminal` widget.

Sequences that only make sense against a genuine two-dimensional screen
buffer (vertical cursor movement, scroll regions, mode toggles, and so
forth) are recognised, stripped from the resolved text and logged (see
:class:`SkippedOp`) rather than raising or being silently discarded without
trace.
"""

from __future__ import annotations

import dataclasses
import logging
import types
import typing

from urwid.display import NO_HYPERLINK, AttrSpec, Hyperlink
from urwid.display.common import _BASIC_COLORS as BASIC_COLORS
from urwid.display.common import _SETTING_OFF_PREFIX
from urwid.display.common import _color_desc_256 as color_desc_256
from urwid.display.common import _color_desc_true as color_desc_true
from urwid.display.escape import ALT_DEC_SPECIAL_CHARS, DEC_SPECIAL_CHARS, DEC_TAG, SI, SO
from urwid.util import rle_append_modify

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Sequence


__all__ = (
    "MAX_CSI_LENGTH",
    "MAX_OSC_LENGTH",
    "OSC_IGNORED_CONTROLS",
    "AnsiParser",
    "CharsetState",
    "ParsedLine",
    "SkippedOp",
    "attrspec_with_hyperlink",
    "led_state",
    "parse_ansi_line",
    "parse_ansi_text",
    "resolve_osc_hyperlink",
    "resolve_osc_title",
    "sgi_params_to_attrspec",
)

LOGGER = logging.getLogger(__name__)

ESC = "\x1b"
BEL = "\x07"

#: Recognised, ready-to-render values of :attr:`ParsedLine.leds`.
LedsLiteral = "Literal['clear', 'scroll_lock', 'num_lock', 'caps_lock']"

_LED_STATES: dict[int, str] = {
    0: "clear",
    1: "scroll_lock",
    2: "num_lock",
    3: "caps_lock",
}

_SGR_ATTR_NAMES: tuple[str, ...] = ("bold", "faint", "italics", "underline", "blink", "standout", "strikethrough")
#: SGR parameter -> the setting it turns on
_SGR_SETS: dict[int, str] = {
    1: "bold",
    2: "faint",
    3: "italics",
    4: "underline",
    5: "blink",
    7: "standout",
    9: "strikethrough",
}
#: SGR parameter -> the settings it turns off
_SGR_RESETS: dict[int, tuple[str, ...]] = {
    22: ("bold", "faint"),
    23: ("italics",),
    24: ("underline",),
    25: ("blink",),
    27: ("standout",),
    29: ("strikethrough",),
}

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

#: The final byte of a G0/G1 designation that selects US ASCII.
_ASCII_SET: typing.Final = "B"

#: fbterm's ``CSI 1;n }`` and ``CSI 2;n }``: the SGR parameters selecting 256-color palette index n as the
#: foreground or the background.
_FBTERM_COLOR_SGR: typing.Final = types.MappingProxyType({1: 38, 2: 48})

#: CAN and SUB, which abort an escape sequence in progress.
_CANCEL = frozenset("\x18\x1a")

#: Control characters a terminal ignores inside an OSC string, unless they follow an ESC there: they are neither
#: executed nor part of the string. DEL is not among them: a terminal keeps it in the string.
OSC_IGNORED_CONTROLS = frozenset(map(chr, range(0x20))) - {BEL, ESC, *_CANCEL}

#: C0 control characters and DEL passed to ``AnsiParser._execute_control()`` wherever they appear outside an OSC
#: string, also inside another escape sequence, which then continues; ESC, CAN, SUB and the line ends are handled apart.
_INLINE_CONTROLS = frozenset(map(chr, (*range(0x20), 0x7F))) - {ESC, *_CANCEL, "\r", "\n"}

#: Line-end byte pairs that collapse into a single structural split point.
_LINE_END_PAIR: dict[str, str] = {"\r": "\n", "\n": "\r"}

#: The furthest a relative cursor move advances, and the furthest 1-based row or column an absolute move reaches.
#: The input is untrusted, and a few bytes such as ``CSI 300000000 C`` would otherwise pad the grid with that many
#: cells. 1024 exceeds the width and height of practical terminals, and caps what one movement sequence adds to the
#: grid at 1024 cells.
_MAX_CURSOR_POSITION = 1024

#: CSI parameter strings of this length or longer are skipped unparsed. Real sequences are far shorter (a truecolour
#: foreground and background SGR is under 50 characters). Staying below 640, the lowest limit
#: :func:`sys.set_int_max_str_digits` accepts, guarantees ``int()`` never rejects a parameter.
MAX_CSI_LENGTH = 256

#: OSC strings of this length or longer are skipped, and the rest of the string up to its terminator, or up to an ESC
#: starting a new sequence, is discarded unbuffered, so an unterminated OSC costs neither memory nor quadratic string
#: growth.
MAX_OSC_LENGTH = 4096

#: The most entries a ``skipped`` list holds, covering one 64 KiB raw display read of 2-byte sequences.
_MAX_SKIPPED = 65536

#: Padding cells a parser may insert regardless of input length, one full 1024 x 1024 screen.
_PADDING_BUDGET = _MAX_CURSOR_POSITION * _MAX_CURSOR_POSITION

#: Padding cells each fed character adds to the budget, as many as a tab writes.
_PADDING_PER_CHARACTER = 8

#: Padding cells an empty row inserted by a vertical move costs, about what the row allocates.
_PADDING_PER_ROW = 8


@dataclasses.dataclass(frozen=True)
class SkippedOp:
    """A single escape-sequence (or control character) that was recognised but stripped.

    Such a sequence is stripped from the resolved text rather than interpreted, because it has no meaning outside a
    full two-dimensional terminal canvas.

    :ivar kind: one of ``"vertical-move"``, ``"terminal-setting"`` or ``"unknown"``.
    :ivar raw: the raw sequence text as encountered (including its ``ESC``/``CSI`` framing), truncated for a sequence
        skipped for its length.
    :ivar reason: a human-readable explanation, used verbatim in the log message emitted alongside this entry.
    """

    kind: str
    raw: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class CharsetState:
    """The character sets designated to G0 and G1, and the one selected, at the end of a parsed line.

    :ivar g0: the final byte of the G0 designation: ``"B"`` for US ASCII, ``"0"`` for DEC Special Graphics.
    :ivar g1: the final byte of the G1 designation, in the same form.
    :ivar selected: ``0`` when G0 is selected (SI), ``1`` when G1 is (SO).
    :raises ValueError: *selected* is neither ``0`` nor ``1``.
    """

    g0: str = _ASCII_SET
    g1: str = DEC_TAG
    selected: typing.Literal[0, 1] = 0

    def __post_init__(self) -> None:
        """Refuse a selected slot other than G0 or G1."""
        if self.selected not in {0, 1}:
            raise ValueError(f"selected must be 0 (G0) or 1 (G1), not {self.selected!r}")


@dataclasses.dataclass(frozen=True)
class ParsedLine:
    r"""The result of parsing one physical line of ANSI-coloured text.

    :ivar text: the resolved, escape-free text of this line. When produced by :class:`AnsiParser` constructed with
        ``one_line=True`` (or :func:`parse_ansi_line`), this is guaranteed never to contain a ``\n`` -- line ends
        are structural split points that produce *separate* :class:`ParsedLine` instances. That invariant is
        deliberately **not** upheld when :class:`AnsiParser` is constructed with ``one_line=False`` (or by
        :func:`parse_ansi_text`): since that mode resolves a whole multi-row block into a single :class:`ParsedLine`,
        its ``text`` legitimately contains embedded ``\n`` characters, one per row boundary, by design.
    :ivar attrib: run-length encoded display attributes for :attr:`text`, the same shape as
        :attr:`urwid.Text.attrib`. ``None`` is a valid RLE tag (meaning "no attribute"), matching
        :func:`urwid.util.decompose_tagmarkup`'s convention.
    :ivar last_attr: the SGR/colour state in effect at the end of this line.
    :ivar bel: the number of BEL (``\a``) characters seen on this line (``0`` if none were seen).
    :ivar title: the last OSC window-title string seen on this line, or ``None`` if none was seen.
    :ivar leds: the last keyboard-LED state requested on this line (``CSI n q``), or ``None`` if none was seen.
    :ivar skipped: the :class:`SkippedOp` entries stripped while parsing this line, in encounter order, for
        programmatic inspection independent of the log. It holds at most the first 65536 of them.
    :ivar last_charsets: the character sets in effect at the end of this line.

    Pass the line itself as ``previous_attr`` to continue both :attr:`last_attr` and :attr:`last_charsets` into a
    subsequently parsed line; passing :attr:`last_attr` alone starts that line with the default character sets.
    """

    text: str
    attrib: list[tuple[Hashable, int]]
    last_attr: AttrSpec | None
    bel: int = 0
    title: str | None = None
    leds: str | None = None
    skipped: list[SkippedOp] = dataclasses.field(default_factory=list)
    last_charsets: CharsetState = CharsetState()


class AnsiParser:
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
    being read, recorded as a :class:`SkippedOp`, and starts a new one.

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
    following backslash still ends the string. An OSC string left unterminated hides the rest of the input.

    Deliberately out of scope in both modes (stripped and logged as :class:`SkippedOp` with
    ``kind="terminal-setting"`` or ``kind="unknown"``): erase (``CSI J``/``K``), scroll regions, save/restore
    cursor, mode toggles, insert/delete, device queries, tabstops, and the non-CSI vertical-movement escapes
    (``ESC D``/``M``/``E``) -- a genuine two-dimensional buffer would technically allow implementing erase and
    save/restore cursor, but that is a candidate follow-up, kept out of scope here. Text sizing (OSC 66) is not
    interpreted either: it is stripped together with the text it carries.

    The padding inserted to reach a moved cursor -- blank cells before a written character and empty rows below the
    last one -- is limited to ``1024 * 1024 + 8 * n`` cells over the parser's lifetime, ``n`` being the number of
    characters fed so far, and an empty row counts as 8 cells. Once the limit is reached, a character is written at the
    end of its row instead, a vertical move past the last row stays on the last row, and each such cut is recorded as
    a :class:`SkippedOp` with ``kind="unknown"``.

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

        # escape-framing state: 0 none / 1 CSI / 2 OSC / 3 two-char intermediate /
        # 4 the discarded remainder of an over-long OSC string
        self._within_escape = False
        self._parsestate = 0
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
        self._padding_budget += _PADDING_PER_CHARACTER * len(text)

        if self._pending_line_end is not None:
            pending = self._pending_line_end
            self._pending_line_end = None
            if text[:1] == _LINE_END_PAIR.get(pending):
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
            if ch in _LINE_END_PAIR:
                if self._parsestate in {2, 4} and self._escbuf[-1:] != ESC:
                    # a line end inside an OSC string is ignored, see _step()
                    i += 1
                    continue
                if self._one_line:
                    # an escape sequence in progress continues on the next line, as in a terminal
                    self._complete_line()
                    if i + 1 < n and text[i + 1] == _LINE_END_PAIR[ch]:
                        i += 2
                    else:
                        if i + 1 == n:
                            self._pending_line_end = ch
                        i += 1
                    continue
                if i + 1 < n and text[i + 1] == _LINE_END_PAIR[ch]:
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
            self._step(ch)
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
        if self._parsestate == 2:
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

    # -- internal: char-by-char state machine ---------------------------

    def _step(self, ch: str) -> None:
        if self._parsestate in {2, 4}:
            if ch in _CANCEL:
                # CAN/SUB abort the string unapplied
                if self._parsestate == 2:
                    self._skip("unknown", f"{ESC}]{self._escbuf.removesuffix(ESC)}", "unterminated OSC string")
                self._leave_escape()
            elif ch not in OSC_IGNORED_CONTROLS:
                self._handle_osc_char(ch)
            elif self._escbuf[-1:] == ESC:
                # after an ESC, as in a terminal and urwid.vterm, the control character is executed and the ESC stays
                # pending, so a following backslash still ends the string; line ends are handled so in feed()
                self._execute_control(ch)
            return
        if ch in _INLINE_CONTROLS:
            self._execute_control(ch)
            return
        if ch in _CANCEL:  # CAN/SUB -- abort any escape in progress
            self._within_escape = False
            self._parsestate = 0
            self._escbuf = ""
            return
        if ch == ESC:
            if self._within_escape:
                # as in a terminal, an ESC drops a sequence still being read and starts a new one
                reason = "escape sequence interrupted by ESC"
                if len(self._escbuf) >= MAX_CSI_LENGTH:
                    reason += f", its CSI parameters of {MAX_CSI_LENGTH} characters or more truncated"
                self._skip("unknown", f"{ESC}{'[' if self._parsestate == 1 else ''}{self._escbuf}", reason)
                self._leave_escape()
            self._within_escape = True
            return
        if self._within_escape:
            self._parse_escape(ch)
            return
        if self._charsets[self._active_charset] == DEC_TAG:
            ch = ch.translate(_DEC_SPECIAL_GRAPHICS)
        self._write_char(ch, self._attrspec)

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

    def _leave_escape(self) -> None:
        self._within_escape = False
        self._parsestate = 0
        self._escbuf = ""

    def _skip(self, kind: str, raw: str, reason: str) -> None:
        """Record a stripped sequence and log it at debug level.

        Entries past the first :data:`_MAX_SKIPPED` are not recorded.
        Untrusted input can repeat a sequence without limit.
        A warning would reach stderr, over the UI, through Python's last-resort handler.
        """
        if len(self._skipped) < _MAX_SKIPPED:
            self._skipped.append(SkippedOp(kind=kind, raw=raw, reason=reason))
        LOGGER.debug("%s: %r", reason, raw)

    def _parse_escape(self, ch: str) -> None:
        if self._parsestate == 1:  # within CSI
            if " " <= ch <= "?":  # parameter and intermediate bytes, ECMA-48 5.4
                # past the limit the parameters are dropped; _dispatch_csi skips the sequence by its length
                if len(self._escbuf) < MAX_CSI_LENGTH:
                    self._escbuf += ch
                return
            self._dispatch_csi(ch, self._escbuf)
            self._leave_escape()
            return

        if self._parsestate == 0 and ch == "]":
            self._escbuf = ""
            self._parsestate = 2
            return

        if self._parsestate == 0 and ch == "[":
            self._escbuf = ""
            self._parsestate = 1
            return

        if self._parsestate == 0 and ch in "%#()":
            self._escbuf = ch
            self._parsestate = 3
            return

        if self._parsestate == 3:
            self._dispatch_noncsi(ch, self._escbuf)
            self._leave_escape()
            return

        if ch in "cDEHMZ78>=":
            self._dispatch_noncsi(ch, "")
        else:
            self._skip("unknown", f"{ESC}{ch}", f"unrecognised escape sequence ESC {ch!r}")
        self._leave_escape()

    def _dispatch_csi(self, final: str, escbuf: str) -> None:
        raw = f"{ESC}[{escbuf}{final}"
        if len(escbuf) >= MAX_CSI_LENGTH:
            self._skip("unknown", raw, f"CSI parameters of {MAX_CSI_LENGTH} characters or more, truncated")
            return

        qmark = escbuf.startswith("?")
        body = escbuf[1:] if qmark else escbuf
        if body.strip("0123456789;"):
            self._skip("unknown", raw, "CSI sub-parameters, private markers and intermediate bytes are not supported")
            return
        params: list[int | None] = [int(p) if p else None for p in body.split(";")] if body else []

        if final == "m":
            ints = [p if p is not None else 0 for p in params] or [0]
            # a color the text leaves unset shows the background or foreground of the widget around it, and bold
            # stays bold: the display brightens it again where the terminal draws bold text in bright colors
            self._attrspec = sgi_params_to_attrspec(ints, self._attrspec, unset_color="inherit", bright_is_bold=False)
        elif (
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

    def _handle_osc_char(self, ch: str) -> None:
        if self._escbuf[-1:] == ESC and ch != "\\":
            # ECMA-48 allows no ESC inside a command string other than in ST, so any other ESC ends the string
            # unapplied and starts a new escape sequence
            if self._parsestate == 2:
                self._skip("unknown", f"{ESC}]{self._escbuf[:-1]}", "unterminated OSC string")
            self._leave_escape()
            self._within_escape = True
            self._step(ch)
            return
        if self._parsestate == 4:
            # only the last character is kept, which is enough to recognise either terminator
            if ch == BEL or (self._escbuf == ESC and ch == "\\"):
                self._leave_escape()
            else:
                self._escbuf = ch
            return
        if ch == BEL:
            self._finish_osc(self._escbuf)
            return
        if self._escbuf[-1:] == ESC and ch == "\\":
            self._finish_osc(self._escbuf[:-1])
            return
        if len(self._escbuf) >= MAX_OSC_LENGTH:
            if self._escbuf.lstrip("0").startswith("8;"):
                # an over-long OSC 8 is refused like any other invalid one, ending the current link
                self._attrspec = attrspec_with_hyperlink(self._attrspec, None, unset_color="inherit")
            self._skip(
                "unknown", f"{ESC}]{self._escbuf}", f"OSC string of {MAX_OSC_LENGTH} characters or more, truncated"
            )
            self._parsestate = 4
            self._escbuf = ch
            return
        if not self._escbuf and ch == "R":
            self._escbuf = ch
            self._finish_osc_skip("OSC palette reset")
            return
        self._escbuf += ch
        # an ESC is no digit: the next character decides whether it starts ST or a new sequence
        if ch != ESC and self._escbuf.startswith("P") and len(self._escbuf) == 8:
            # the Linux console's palette set, ESC ] P n rr gg bb, ends with its 7th hex digit
            self._finish_osc_skip("OSC palette set")

    def _finish_osc(self, buf: str) -> None:
        raw = f"{ESC}]{buf}"
        self._leave_escape()
        title = resolve_osc_title(buf)
        if title is not None:
            self._title = title
            return
        try:
            link = resolve_osc_hyperlink(buf)
        except ValueError:
            # the text after it must not keep pointing at the previous link
            self._attrspec = attrspec_with_hyperlink(self._attrspec, None, unset_color="inherit")
            self._skip("unknown", raw, "invalid OSC 8 hyperlink, current link ended")
            return
        if link is not None:
            self._attrspec = attrspec_with_hyperlink(self._attrspec, link, unset_color="inherit")
        else:
            self._skip("terminal-setting", raw, "unrecognised OSC prefix")

    def _finish_osc_skip(self, reason: str) -> None:
        raw = f"{ESC}]{self._escbuf}"
        self._skip("terminal-setting", raw, reason)
        self._leave_escape()


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


def led_state(mode: int) -> str | None:
    """Map a keyboard-LED ``CSI n q`` mode number to its urwid-facing state name.

    Shared by :class:`AnsiParser` and :mod:`urwid.vterm`'s ``TermCanvas.csi_set_keyboard_leds`` so the LED code
    mapping is maintained in exactly one place.

    :param mode: the ``CSI n q`` mode number to resolve.
    :returns: one of ``"clear"``, ``"scroll_lock"``, ``"num_lock"`` or ``"caps_lock"``, or ``None`` if ``mode`` is
        not recognised.

    >>> led_state(0)
    'clear'
    >>> led_state(3)
    'caps_lock'
    >>> led_state(99) is None
    True
    """
    return _LED_STATES.get(mode)


def resolve_osc_title(buf: str) -> str | None:
    """Resolve the window-title text encoded in an OSC command body, if it matches a recognised title prefix.

    Applies the same prefix rules xterm and :mod:`urwid.vterm` use to recognise an OSC window-title request -- a
    body starting (after stripping leading zeros) with ``;``, ``0;`` or ``2;`` -- and returns the text following
    the first ``;``. Returns ``None`` for any other OSC body (e.g. an unrecognised or palette-setting OSC), rather
    than raising.

    :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
    :returns: the resolved window-title text, or ``None`` if ``buf`` does not match a recognised title prefix.

    >>> resolve_osc_title(";hello")
    'hello'
    >>> resolve_osc_title("2;hello")
    'hello'
    >>> resolve_osc_title("666not a title") is None
    True
    """
    stripped = buf.lstrip("0")
    if stripped.startswith((";", "0;", "2;")):
        return stripped.partition(";")[2]
    return None


def resolve_osc_hyperlink(buf: str) -> Hyperlink | None:
    """Resolve the hyperlink an OSC 8 command body starts or ends.

    The body is ``8;params;URI`` after leading zeros are stripped, as :func:`resolve_osc_title` strips them.
    *params* are ``key=value`` pairs separated by ``:``; ``id`` is used and other keys are ignored,
    as the OSC 8 specification asks.

    :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
    :returns: the link the following text is drawn with, :data:`~urwid.NO_HYPERLINK` when the body ends the link
        (an empty URI), or ``None`` when ``buf`` is not an OSC 8 command.
    :raises ValueError: ``buf`` is an OSC 8 command without the URI field,
        or with a URI or id :class:`~urwid.Hyperlink` refuses.

    >>> resolve_osc_hyperlink("8;id=home;https://urwid.org")
    Hyperlink(uri='https://urwid.org', id='home')
    >>> resolve_osc_hyperlink("8;;") is NO_HYPERLINK
    True
    >>> resolve_osc_hyperlink("2;title") is None
    True
    """
    stripped = buf.lstrip("0")
    if not stripped.startswith("8;"):
        return None
    params, sep, uri = stripped[2:].partition(";")
    if not sep:
        raise ValueError(f"OSC 8 command without a URI field: {buf!r}")
    if not uri:
        return NO_HYPERLINK
    link_id = ""
    for param in params.split(":"):
        key, _, value = param.partition("=")
        if key == "id":
            link_id = value
    return Hyperlink(uri, id=link_id)


def attrspec_with_hyperlink(
    attrspec: AttrSpec | None,
    link: Hyperlink | None,
    *,
    unset_color: typing.Literal["default", "inherit"],
) -> AttrSpec | None:
    """Return *attrspec* with its hyperlink replaced by *link*, in the form :func:`sgi_params_to_attrspec` returns.

    :data:`~urwid.NO_HYPERLINK` and ``None`` both mean that the text has no link of its own.
    The result is a plain :class:`~urwid.AttrSpec`, as from :func:`sgi_params_to_attrspec`, so a subclass of
    *attrspec* whose constructor takes no *hyperlink* keyword cannot make parsing raise.

    :param attrspec: the attribute in effect, or ``None`` for "no attributes".
    :param link: the link to set, :data:`~urwid.NO_HYPERLINK` or ``None`` to remove the link.
    :param unset_color: the color of a foreground or background no SGR parameter has set, as for
        :func:`sgi_params_to_attrspec`.
    :returns: the resulting attribute, or ``None`` when it sets neither colors, settings nor a link.

    >>> attrspec_with_hyperlink(None, Hyperlink("https://urwid.org"), unset_color="inherit")
    AttrSpec('inherit', 'inherit', hyperlink=Hyperlink(uri='https://urwid.org', id=''))
    >>> attrspec_with_hyperlink(AttrSpec(hyperlink="https://urwid.org"), None, unset_color="inherit") is None
    True
    """
    if link == NO_HYPERLINK:
        link = None
    if attrspec is None:
        if link is None:
            return None
        return AttrSpec(unset_color, unset_color, hyperlink=link)
    if link is None and attrspec.foreground == attrspec.background == unset_color:
        return None
    return AttrSpec(attrspec.foreground, attrspec.background, attrspec.colors, hyperlink=link)


def sgi_params_to_attrspec(
    params: Sequence[int],
    previous: AttrSpec | None,
    *,
    unset_color: typing.Literal["default", "inherit"] = "default",
    bright_is_bold: bool = True,
) -> AttrSpec | None:
    """Resolve a sequence of SGR (Select Graphic Rendition) numeric parameters against a previous attribute spec.

    Ignore unsupported parameters and extended colors with an out-of-range value.
    Charset parameters 10-12 are handled by the caller.
    The hyperlink of *previous* is kept, also through SGR 0, since OSC 8 sets it independently of SGR.

    :param params: the SGR numeric parameters to apply, in encounter order.
    :param previous: the :class:`~urwid.AttrSpec` in effect before ``params`` is applied, or ``None`` if none is
        in effect yet.
    :param unset_color: the color given to a foreground or background no parameter has set, or SGR 39/49/0 reset:
        'default' for the terminal default, 'inherit' for the color of the enclosing attribute.
        With 'inherit', SGR 22/23/24/25/27/29 turn their settings off ('no-bold') rather than leaving them to the
        enclosing attribute, and SGR 0 leaves every setting to it again.
    :param bright_is_bold: whether bold also selects the bright variant of a basic foreground when the attribute
        uses only the 16 basic colors, as on a terminal that draws bold text in bright colors; if false, bold stays
        a setting of its own.
    :returns: the resulting :class:`~urwid.AttrSpec`, or ``None`` for "no attributes".

    >>> sgi_params_to_attrspec([31], None)
    AttrSpec('dark red', 'default')
    >>> sgi_params_to_attrspec([0], AttrSpec("dark red", "default"))
    >>> sgi_params_to_attrspec([31], None, unset_color="inherit")
    AttrSpec('dark red', 'inherit')
    >>> sgi_params_to_attrspec([24], None, unset_color="inherit")
    AttrSpec('inherit,no-underline', 'inherit')
    >>> sgi_params_to_attrspec([31, 1], None)
    AttrSpec('light red,bold', 'default')
    >>> sgi_params_to_attrspec([31, 1], None, bright_is_bold=False)
    AttrSpec('dark red,bold', 'default')
    """
    hyperlink = None if previous is None else previous.hyperlink

    attributes: set[str] = set()
    # settings an SGR reset turned off; with 'inherit' colors they stay off over the enclosing attribute
    turned_off: set[str] = set()
    # fg/bg hold a palette index (0-255), or a 0xRRGGBB value when fg_rgb/bg_rgb is set.
    fg_rgb = bg_rgb = False
    if previous is None:
        fg: int | None = None
        bg: int | None = None
        colors: int = 1
    else:
        for name in _SGR_ATTR_NAMES:
            if getattr(previous, name):
                attributes.add(name)
        turned_off.update(
            part.removeprefix(_SETTING_OFF_PREFIX)
            for part in previous.foreground.split(",")
            if part.startswith(_SETTING_OFF_PREFIX)
        )

        has_fg = previous.foreground_basic or previous.foreground_high or previous.foreground_true
        fg = previous.foreground_number if has_fg else None
        fg_rgb = previous.foreground_true
        # undo the bold brightening applied below, so it can be reapplied or dropped with the new bold state
        if bright_is_bold and fg is not None and fg >= 8 and previous.colors == 16 and "bold" in attributes:
            fg -= 8

        has_bg = previous.background_basic or previous.background_high or previous.background_true
        bg = previous.background_number if has_bg else None
        bg_rgb = previous.background_true

        colors = previous.colors

    params = list(params)
    idx = 0
    while idx < len(params):
        attr = params[idx]
        if 30 <= attr <= 37:
            fg, fg_rgb = attr - 30, False
            colors = max(16, colors)
        elif 40 <= attr <= 47:
            bg, bg_rgb = attr - 40, False
            colors = max(16, colors)
        elif 90 <= attr <= 97:
            fg, fg_rgb = attr - 90 + 8, False
            colors = max(16, colors)
        elif 100 <= attr <= 107:
            bg, bg_rgb = attr - 100 + 8, False
            colors = max(16, colors)
        elif attr in (38, 48):
            if idx + 2 < len(params) and params[idx + 1] == 5:
                color = params[idx + 2]
                if 0 <= color <= 255:
                    colors = max(256, colors)
                    if attr == 38:
                        fg, fg_rgb = color, False
                    else:
                        bg, bg_rgb = color, False
                idx += 2
            elif idx + 4 < len(params) and params[idx + 1] == 2:
                if all(0 <= component <= 255 for component in params[idx + 2 : idx + 5]):
                    color = (params[idx + 2] << 16) + (params[idx + 3] << 8) + params[idx + 4]
                    colors = 16777216  # 2 ** 24
                    if attr == 38:
                        fg, fg_rgb = color, True
                    else:
                        bg, bg_rgb = color, True
                idx += 4
        elif attr == 39:
            fg = None
        elif attr == 49:
            bg = None
        elif attr in (10, 11, 12):
            # vterm-only charset/display-control side effects; left to the caller
            pass
        elif attr in _SGR_SETS:
            attributes.add(_SGR_SETS[attr])
            turned_off.discard(_SGR_SETS[attr])
        elif attr in _SGR_RESETS:
            attributes.difference_update(_SGR_RESETS[attr])
            turned_off.update(_SGR_RESETS[attr])
        elif attr == 0:
            fg = bg = None
            fg_rgb = bg_rgb = False
            colors = 1
            attributes.clear()
            turned_off.clear()
        idx += 1

    if bright_is_bold and "bold" in attributes and colors == 16 and fg is not None and fg < 8:
        fg += 8

    def _defaulter(req_color: int | None, rgb: bool) -> str:
        if req_color is None:
            return unset_color
        if rgb:
            return color_desc_true(req_color)
        # Note: 88-colour mode cannot be distinguished from 256-colour mode here.
        # A true-colour AttrSpec converts a palette name to its RGB value itself.
        if req_color > 15 or colors == 256:
            return color_desc_256(req_color)
        return BASIC_COLORS[req_color]

    decoded_fg = _defaulter(fg, fg_rgb)
    decoded_bg = _defaulter(bg, bg_rgb)

    if unset_color == "inherit":
        attributes.update(f"{_SETTING_OFF_PREFIX}{name}" for name in turned_off)
    if attributes:
        decoded_fg = ",".join((decoded_fg, *sorted(attributes)))

    if decoded_fg == decoded_bg == unset_color and hyperlink is None:
        return None

    if colors:
        # `colors` is only ever assigned one of AttrSpec's accepted literals above (1, 16, 88 -- via
        # `previous.colors` --, 256 or 16777216), but the running total is tracked as a plain `int`
        # through the `max()` calls, so the literal type is lost to mypy; the cast restores it.
        return AttrSpec(
            decoded_fg,
            decoded_bg,
            colors=typing.cast("typing.Literal[1, 16, 88, 256, 16777216]", colors),
            hyperlink=hyperlink,
        )

    return AttrSpec(decoded_fg, decoded_bg, hyperlink=hyperlink)
