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
title and keyboard-LED recognition -- into a form that can be used to
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
import typing

from urwid.display import AttrSpec
from urwid.display.common import _BASIC_COLORS as BASIC_COLORS
from urwid.display.common import _color_desc_256 as color_desc_256
from urwid.display.common import _color_desc_true as color_desc_true
from urwid.util import rle_append_modify

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Sequence


__all__ = (
    "AnsiParser",
    "ParsedLine",
    "SkippedOp",
    "led_state",
    "parse_ansi_line",
    "parse_ansi_text",
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

_SGR_ATTR_NAMES: tuple[str, ...] = ("bold", "faint", "underline", "blink", "standout")

#: CSI final bytes that move the cursor vertically -- meaningless outside a
#: two-dimensional screen buffer, so the whole operation is stripped and
#: logged rather than reinterpreted.
_VERTICAL_MOVE_CSI = frozenset("ABEFdHf")

#: CSI final bytes that mutate terminal-wide state (modes, scroll regions,
#: erase, insert/delete, device queries, tabstops, ...) -- again meaningless
#: for a single, canvas-less line of text.
_TERMINAL_SETTING_CSI = frozenset("hlrJKsu@LMPXcng")

#: Line-end byte pairs that collapse into a single structural split point.
_LINE_END_PAIR: dict[str, str] = {"\r": "\n", "\n": "\r"}


@dataclasses.dataclass(frozen=True)
class SkippedOp:
    """A single escape-sequence (or control character) that was recognised but stripped.

    Such a sequence is stripped from the resolved text rather than interpreted, because it has no meaning outside a
    full two-dimensional terminal canvas.

    :ivar kind: one of ``"vertical-move"``, ``"terminal-setting"`` or ``"unknown"``.
    :ivar raw: the raw sequence text as encountered (including its ``ESC``/``CSI`` framing).
    :ivar reason: a human-readable explanation, used verbatim in the log message emitted alongside this entry.
    """

    kind: str
    raw: str
    reason: str


@dataclasses.dataclass(frozen=True)
class ParsedLine:
    """The result of parsing one physical line of ANSI-coloured text.

    :ivar text: the resolved, escape-free text of this line. When produced by :class:`AnsiParser` constructed with
        ``one_line=True`` (or :func:`parse_ansi_line`), this is guaranteed never to contain a ``\\n`` -- line ends
        are structural split points that produce *separate* :class:`ParsedLine` instances. That invariant is
        deliberately **not** upheld when :class:`AnsiParser` is constructed with ``one_line=False`` (or by
        :func:`parse_ansi_text`): since that mode resolves a whole multi-row block into a single :class:`ParsedLine`,
        its ``text`` legitimately contains embedded ``\\n`` characters, one per row boundary, by design.
    :ivar attrib: run-length encoded display attributes for :attr:`text`, the same shape as
        :attr:`urwid.Text.attrib`. ``None`` is a valid RLE tag (meaning "no attribute"), matching
        :func:`urwid.util.decompose_tagmarkup`'s convention.
    :ivar last_attr: the SGR/colour state in effect at the end of this line; feed this back in as ``previous_attr``
        to continue the same colour state into a subsequently parsed line.
    :ivar bel: the number of BEL (``\\a``) characters seen on this line (``0`` if none were seen).
    :ivar title: the last OSC window-title string seen on this line, or ``None`` if none was seen.
    :ivar leds: the last keyboard-LED state requested on this line (``CSI n q``), or ``None`` if none was seen.
    :ivar skipped: every :class:`SkippedOp` stripped while parsing this line, in encounter order, for programmatic
        inspection independent of the log.
    """

    text: str
    attrib: list[tuple[Hashable, int]]
    last_attr: AttrSpec | None
    bel: int = 0
    title: str | None = None
    leds: str | None = None
    skipped: list[SkippedOp] = dataclasses.field(default_factory=list)


class AnsiParser:
    """Incremental ANSI parser that resolves escape sequences against a 2-D cell grid, in one of two modes.

    Feed text in with :meth:`feed` -- any number of times, e.g. as chunks arrive from a subprocess -- and call
    :meth:`finalize` once to retrieve the result. :meth:`finalize` is a one-shot, terminal operation: construct a
    fresh :class:`AnsiParser` per logical "session" of feeding.

    Internally, a :class:`AnsiParser` always maintains a two-dimensional grid of rows (one cell buffer per screen
    row) plus a cursor (``row``, ``col``). The two constructor modes below share the *overwhelming majority* of
    their behaviour -- printable characters, horizontal cursor movement (``CSI n C/D/G``), backspace, tab, SGR
    colour/attribute handling (``CSI ... m``), BEL, OSC window-title recognition, keyboard-LED requests
    (``CSI n q``) and terminal-wide setting sequences (stripped and logged, see :class:`SkippedOp`) are interpreted
    identically regardless of mode. They differ only in how a **line end** and **vertical cursor movement** are
    treated, and in whether the side channels (``bel``, ``title``, ``leds``, ``skipped``) are reset per line or
    aggregated over the whole input:

    * ``one_line=True``: a line-end sequence (``\\n``, ``\\r``, ``\\r\\n`` or ``\\n\\r``, the latter two pairs
      collapsing into a single event) is a **structural split point**, not discarded data -- the moment one is
      seen, the current row is completed into a :class:`ParsedLine` and pushed onto an internal completed-lines
      queue, and a fresh row is started for what follows, carrying the SGR/colour state
      (:attr:`ParsedLine.last_attr`) forward but resetting the per-line side channels. Vertical cursor movement
      (``CSI n A/B/E/F/d`` and ``CSI r;c H``/``f``) is meaningless outside a single line, so it is stripped and
      logged as a :class:`SkippedOp` rather than reinterpreted.
    * ``one_line=False`` (the default): a full newline (``\\n``, or a collapsed ``\\r\\n``/``\\n\\r`` pair) genuinely
      moves to a fresh row, resetting the column, while everything keeps accumulating in the same persistent grid
      -- nothing is split off. A **bare** ``\\r`` (not part of a ``\\r\\n``/``\\n\\r`` pair) is carriage-return-only:
      it resets the column without changing row, letting progress-bar-style in-place redraw sequences
      (``"progress: 10%\\rprogress: 20%"``) resolve correctly onto a single row, mirroring real terminal behaviour.
      Vertical cursor movement genuinely repositions the cursor within the grid instead of being stripped. The side
      channels are aggregated over the *entire* input rather than reset per row: ``bel`` is the total BEL count,
      ``title``/``leds`` are the last value seen anywhere, and ``skipped`` lists every :class:`SkippedOp` in
      encounter order.

    Deliberately out of scope in both modes (stripped and logged as :class:`SkippedOp` with
    ``kind="terminal-setting"`` or ``kind="unknown"``): erase (``CSI J``/``K``), scroll regions, save/restore
    cursor, mode toggles, insert/delete, device queries, tabstops, and the non-CSI vertical-movement escapes
    (``ESC D``/``M``/``E``) -- a genuine two-dimensional buffer would technically allow implementing erase and
    save/restore cursor, but that is a candidate follow-up, kept out of scope here.

    :meth:`finalize` returns a uniform ``tuple[ParsedLine, ...]`` in both modes: in ``one_line=True`` mode, every
    line completed since construction (queue plus a final flush of whatever remains, possibly empty or
    unterminated); in ``one_line=False`` mode, always exactly one :class:`ParsedLine` -- built from the whole grid,
    rows joined with ``"\\n"`` -- wrapped in a 1-tuple.

    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from previously
        parsed text.
    :param one_line: if true, treat line ends as structural split points that yield multiple :class:`ParsedLine`
        results; if false (the default), resolve the whole input into a single multi-row :class:`ParsedLine`.

    >>> parser = AnsiParser(one_line=True)
    >>> parser.feed("hello\\nworld")
    >>> [line.text for line in parser.finalize()]
    ['hello', 'world']

    >>> parser = AnsiParser()
    >>> parser.feed("hello\\nworld")
    >>> parser.finalize()[0].text
    'hello\\nworld'
    """

    def __init__(self, previous_attr: AttrSpec | None = None, *, one_line: bool = False) -> None:
        self._one_line = one_line
        self._attrspec: AttrSpec | None = previous_attr

        # one cell buffer per screen row, plus a 2-D cursor -- in one_line
        # mode there is conceptually only ever one row: it is snapshotted
        # and reset at each structural split, see _complete_line()
        self._rows: list[list[tuple[str, Hashable | None]]] = [[]]
        self._row = 0
        self._col = 0

        # side channels -- reset per completed line in one_line mode (see
        # _complete_line()), aggregated over the entire input otherwise
        self._bel_count = 0
        self._title: str | None = None
        self._leds: str | None = None
        self._skipped: list[SkippedOp] = []

        # completed-lines queue, used only in one_line mode
        self._completed: list[ParsedLine] = []

        # escape-framing state: 0 none / 1 CSI / 2 OSC / 3 two-char intermediate
        self._within_escape = False
        self._parsestate = 0
        self._escbuf = ""

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
                if self._one_line:
                    self._handle_line_end()
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
        """Retrieve the parsed result, in a uniform ``tuple[ParsedLine, ...]`` shape regardless of mode.

        In ``one_line=True`` mode, whatever remains in the current (possibly empty, possibly unterminated) row is
        flushed as one final :class:`ParsedLine`, and every line completed since construction is returned, in
        order. In ``one_line=False`` mode, the whole accumulated grid is resolved into a single :class:`ParsedLine`
        (its ``text`` joining every resolved row with ``"\\n"``) and returned as a 1-tuple.

        This is a terminal operation: construct a new :class:`AnsiParser` to parse a fresh "session" of input.

        :returns: a uniform ``tuple[ParsedLine, ...]``, shaped as described above.
        """
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
            skipped=list(self._skipped),
        )
        return (parsed,)

    # -- internal: line/row completion and cursor management -------------

    def _handle_line_end(self) -> None:
        """Complete the current line, aborting any in-flight escape sequence.

        Only called in one_line mode: a line end always aborts any in-flight escape sequence, since real escape
        sequences never legitimately contain a raw \\r or \\n. In screen mode a newline is instead handled directly
        in :meth:`feed` without touching escape-framing state.
        """
        self._within_escape = False
        self._parsestate = 0
        self._escbuf = ""
        self._complete_line()

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
            )
        )

        self._rows = [[]]
        self._col = 0
        self._bel_count = 0
        self._title = None
        self._leds = None
        self._skipped = []

    def _ensure_row(self, row: int) -> None:
        while len(self._rows) <= row:
            self._rows.append([])

    def _newline(self) -> None:
        self._row += 1
        self._ensure_row(self._row)
        self._col = 0

    # -- internal: char-by-char state machine ---------------------------

    def _step(self, ch: str) -> None:
        if self._parsestate == 2:
            self._handle_osc_char(ch)
            return
        if ch == BEL:
            self._bel_count += 1
            return
        if ch == "\t":
            self._handle_tab()
            return
        if ch == "\b":
            self._col = max(0, self._col - 1)
            return
        if ch in ("\x00", "\x7f"):  # NUL/DEL -- ignored, matching vterm
            return
        if ch in ("\x18", "\x1a"):  # CAN/SUB -- abort any escape in progress
            self._within_escape = False
            self._parsestate = 0
            self._escbuf = ""
            return
        if ch == ESC:
            self._within_escape = True
            return
        if self._within_escape:
            self._parse_escape(ch)
            return
        self._write_char(ch, self._attrspec)

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
            while len(row) < self._col:
                row.append((" ", None))
            row.append((ch, attr))
        self._col += 1

    # -- internal: escape/CSI/OSC framing --------------------------------

    def _leave_escape(self) -> None:
        self._within_escape = False
        self._parsestate = 0
        self._escbuf = ""

    def _skip(self, kind: str, raw: str, reason: str) -> None:
        self._skipped.append(SkippedOp(kind=kind, raw=raw, reason=reason))
        message = f"{reason}: {raw!r}"
        if kind == "unknown":
            LOGGER.warning(message)
        else:
            LOGGER.info(message)

    def _parse_escape(self, ch: str) -> None:
        if self._parsestate == 1:  # within CSI
            if ch in "0123456789;" or (not self._escbuf and ch == "?"):
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
        qmark = escbuf.startswith("?")
        body = escbuf[1:] if qmark else escbuf
        params: list[int | None] = [int(p) if p else None for p in body.split(";")] if body else []
        raw = f"{ESC}[{escbuf}{final}"

        if final == "m":
            ints = [p if p is not None else 0 for p in params] or [0]
            self._attrspec = sgi_params_to_attrspec(ints, self._attrspec)
        elif final == "C":
            n = params[0] if params and params[0] else 1
            self._col += n
        elif final == "D":
            n = params[0] if params and params[0] else 1
            self._col = max(0, self._col - n)
        elif final == "G":
            n = params[0] if params and params[0] else 1
            self._col = max(0, n - 1)
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

        # these genuinely reposition the cursor within the grid
        if final == "A":
            n = params[0] if params and params[0] else 1
            self._row = max(0, self._row - n)
        elif final == "B":
            n = params[0] if params and params[0] else 1
            self._row += n
            self._ensure_row(self._row)
        elif final == "E":
            n = params[0] if params and params[0] else 1
            self._row += n
            self._ensure_row(self._row)
            self._col = 0
        elif final == "F":
            n = params[0] if params and params[0] else 1
            self._row = max(0, self._row - n)
            self._col = 0
        elif final == "d":
            n = params[0] if params and params[0] else 1
            self._row = max(0, n - 1)
            self._ensure_row(self._row)
        elif final in ("H", "f"):
            r = params[0] if params and params[0] else 1
            c = params[1] if len(params) > 1 and params[1] else 1
            self._row = max(0, r - 1)
            self._ensure_row(self._row)
            self._col = max(0, c - 1)

    def _dispatch_noncsi(self, ch: str, mod: str) -> None:
        raw = f"{ESC}{mod}{ch}"
        if mod == "#" and ch == "8":
            self._skip("terminal-setting", raw, "DECALN screen alignment test")
        elif mod == "%":
            self._skip("terminal-setting", raw, "character set selection")
        elif mod in ("(", ")"):
            self._skip("terminal-setting", raw, "charset designation")
        elif ch == "M":
            self._skip("vertical-move", raw, "reverse line feed")
        elif ch == "D":
            self._skip("vertical-move", raw, "line feed")
        elif ch == "E":
            self._skip("vertical-move", raw, "newline")
        elif ch == "H":
            self._skip("terminal-setting", raw, "set tabstop")
        elif ch == "c":
            self._skip("terminal-setting", raw, "terminal reset")
        elif ch in ("7", "8"):
            self._skip("terminal-setting", raw, "save/restore cursor")
        elif ch in (">", "=", "Z"):
            self._skip("terminal-setting", raw, "keypad mode / device attributes")
        else:
            self._skip("unknown", raw, f"unrecognised escape sequence {raw!r}")

    def _handle_osc_char(self, ch: str) -> None:
        if ch == BEL:
            self._finish_osc(self._escbuf)
            return
        if self._escbuf[-1:] == ESC and ch == "\\":
            self._finish_osc(self._escbuf[:-1])
            return
        if self._escbuf.startswith("P") and len(self._escbuf) == 8:
            self._finish_osc_skip("OSC palette set")
            return
        if not self._escbuf and ch == "R":
            self._finish_osc_skip("OSC palette reset")
            return
        self._escbuf += ch

    def _finish_osc(self, buf: str) -> None:
        raw = f"{ESC}]{buf}"
        self._leave_escape()
        title = resolve_osc_title(buf)
        if title is not None:
            self._title = title
        else:
            self._skip("terminal-setting", raw, "unrecognised OSC prefix")

    def _finish_osc_skip(self, reason: str) -> None:
        raw = f"{ESC}]{self._escbuf}"
        self._skip("terminal-setting", raw, reason)
        self._leave_escape()


def parse_ansi_line(text: str, previous_attr: AttrSpec | None = None) -> tuple[ParsedLine, ...]:
    """Feed ``text`` through a fresh :class:`AnsiParser` (``one_line=True``) and return its finalised result.

    Returns one :class:`ParsedLine` per line found in ``text`` (split on ``\\n``/``\\r``/``\\r\\n``/``\\n\\r``), plus
    a trailing entry for a final unterminated fragment, if any -- never fewer than one element, even for empty
    input, and every character of the original data is preserved across the returned lines (line-end characters are
    structural split points, not stripped content).

    :param text: the text to parse.
    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from a
        previously parsed line.
    :returns: every :class:`ParsedLine` found in ``text``, in order.

    >>> [line.text for line in parse_ansi_line("one\\ntwo\\nthree")]
    ['one', 'two', 'three']
    >>> [line.text for line in parse_ansi_line("")]
    ['']
    >>> [line.text for line in parse_ansi_line("a\\nb")]
    ['a', 'b']
    """
    parser = AnsiParser(previous_attr, one_line=True)
    parser.feed(text)
    return parser.finalize()


def parse_ansi_text(text: str, previous_attr: AttrSpec | None = None) -> ParsedLine:
    """Feed ``text`` through a fresh :class:`AnsiParser` (``one_line=False``) and return its sole resolved line.

    Unlike :func:`parse_ansi_line`, vertical cursor movement and newlines are resolved into real multi-row output
    rather than stripped/split: the returned single :class:`ParsedLine`'s ``text`` joins every resolved row with
    ``"\\n"``.

    :param text: the text to parse.
    :param previous_attr: SGR/colour state to seed the parser with, as if it were carried over from previously
        parsed text.
    :returns: a single :class:`ParsedLine` representing the whole resolved block.

    >>> parse_ansi_text("one\\ntwo\\nthree").text
    'one\\ntwo\\nthree'
    >>> parse_ansi_text("").text
    ''
    >>> parse_ansi_text("progress: 10%\\rprogress: 20%").text
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


def sgi_params_to_attrspec(params: Sequence[int], previous: AttrSpec | None) -> AttrSpec | None:
    """Resolve a sequence of SGR (Select Graphic Rendition) numeric parameters against a previous attribute spec.

    This is a pure extraction of the SGR-number-walking logic historically duplicated inside
    ``vterm.TermCanvas.sgi_to_attrspec``. SGR 10/11/12 (which toggle vterm's charset/display-control state rather
    than colour/attributes) are deliberately ignored here -- a caller that also needs that side effect applies it
    itself; this function never raises for an unrecognised numeric code, it simply has no effect on the result.

    :param params: the SGR numeric parameters to apply, in encounter order.
    :param previous: the :class:`~urwid.AttrSpec` in effect before ``params`` is applied, or ``None`` if none is
        in effect yet.
    :returns: the resulting :class:`~urwid.AttrSpec`, or ``None`` for "no attributes".

    >>> sgi_params_to_attrspec([31], None)
    AttrSpec('dark red', 'default')
    >>> sgi_params_to_attrspec([0], AttrSpec("dark red", "default"))
    """
    if params and params[-1] == 0:
        previous = None

    attributes: set[str] = set()
    if previous is None:
        fg: int | None = None
        bg: int | None = None
        colors: int = 1
    else:
        fg = None if "default" in previous.foreground else previous.foreground_number
        if fg is not None and fg >= 8 and previous.colors == 16:
            fg -= 8

        bg = None if "default" in previous.background else previous.background_number
        if bg is not None and bg >= 8 and previous.colors == 16:
            bg -= 8

        for name in _SGR_ATTR_NAMES:
            if getattr(previous, name):
                attributes.add(name)

        colors = previous.colors

    params = list(params)
    idx = 0
    while idx < len(params):
        attr = params[idx]
        if 30 <= attr <= 37:
            fg = attr - 30
            colors = max(16, colors)
        elif 40 <= attr <= 47:
            bg = attr - 40
            colors = max(16, colors)
        elif 90 <= attr <= 97:
            fg = attr - 90 + 8
            colors = max(16, colors)
        elif 100 <= attr <= 107:
            bg = attr - 100 + 8
            colors = max(16, colors)
        elif attr in (38, 48):
            if idx + 2 < len(params) and params[idx + 1] == 5:
                color = params[idx + 2]
                colors = max(256, colors)
                if attr == 38:
                    fg = color
                else:
                    bg = color
                idx += 2
            elif idx + 4 < len(params) and params[idx + 1] == 2:
                color = (params[idx + 2] << 16) + (params[idx + 3] << 8) + params[idx + 4]
                colors = 16777216  # 2 ** 24
                if attr == 38:
                    fg = color
                else:
                    bg = color
                idx += 4
        elif attr == 39:
            fg = None
        elif attr == 49:
            bg = None
        elif attr in (10, 11, 12):
            # vterm-only charset/display-control side effects; left to the caller
            pass
        elif attr == 1:
            attributes.add("bold")
        elif attr == 2:
            attributes.add("faint")
        elif attr == 4:
            attributes.add("underline")
        elif attr == 5:
            attributes.add("blink")
        elif attr == 7:
            attributes.add("standout")
        elif attr == 22:
            attributes.discard("bold")
            attributes.discard("faint")
        elif attr == 24:
            attributes.discard("underline")
        elif attr == 25:
            attributes.discard("blink")
        elif attr == 27:
            attributes.discard("standout")
        elif attr == 0:
            fg = bg = None
            attributes.clear()
        idx += 1

    if "bold" in attributes and colors == 16 and fg is not None and fg < 8:
        fg += 8

    def _defaulter(req_color: int | None) -> str:
        if req_color is None:
            return "default"
        # Note: 88-colour mode cannot be distinguished from 256-colour mode here
        if req_color > 255 or colors == 2**24:
            return color_desc_true(req_color)
        if req_color > 15 or colors == 256:
            return color_desc_256(req_color)
        return BASIC_COLORS[req_color]

    decoded_fg = _defaulter(fg)
    decoded_bg = _defaulter(bg)

    if attributes:
        decoded_fg = ",".join((decoded_fg, *attributes))

    if decoded_fg == decoded_bg == "default":
        return None

    if colors:
        # `colors` is only ever assigned one of AttrSpec's accepted literals above (1, 16, 88 -- via
        # `previous.colors` --, 256 or 16777216), but the running total is tracked as a plain `int`
        # through the `max()` calls, so the literal type is lost to mypy; the cast restores it.
        return AttrSpec(decoded_fg, decoded_bg, colors=typing.cast("typing.Literal[1, 16, 88, 256, 16777216]", colors))

    return AttrSpec(decoded_fg, decoded_bg)
