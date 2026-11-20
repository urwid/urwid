# Urwid canvas class and functions
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


"""Text canvas, and the function that lays out text and attributes on it."""

from __future__ import annotations

import dataclasses
import itertools
import re
import typing

import wcwidth

from urwid.canvas._base import Canvas, CanvasError
from urwid.str_util import calc_width, get_byte_encoding
from urwid.text_layout import LayoutSegment, trim_line
from urwid.util import (
    apply_target_encoding,
    get_encoding,
    rle_append_modify,
    rle_join_modify,
    rle_len,
    rle_product,
    trim_text_attr_cs,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
    from typing import Literal

    from urwid.canvas._base import _ContentLine


class TextCanvas(Canvas):
    """class for storing rendered text and attributes."""

    __slots__ = (
        "_attr",
        "_cs",
        "_maxcol",
        "_text",
    )

    def __init__(
        self,
        text: list[bytes] | None = None,
        attr: list[list[tuple[Hashable, int]]] | None = None,
        cs: list[list[tuple[Literal["0", "U"] | None, int]]] | None = None,
        cursor: tuple[int, int] | None = None,
        maxcol: int | None = None,
        check_width: bool = True,
    ) -> None:
        """Build a text canvas from the given lines and attributes.

        Each line of *text* is padded with spaces to *maxcol* columns.
        *attr* and *cs* hold one list of runs per line.
        A run is a ``(value, length)`` tuple that applies *value* to the next *length* bytes of the line.
        The runs of a line cover it from its first byte, and their lengths add up to at most the padded line's length.
        The bytes after the last run, and every line with no list of runs, get ``None``:
        the default attribute, or the default character set.

        For example, ``attr=[[("bold", 3), ("red", 2)], [("blue", 4)]]`` with ``text=[b"foobar", b"test string"]``
        shows ``foo`` as ``bold``, ``ba`` as ``red``, ``r`` with the default attribute, ``test`` as ``blue``,
        and the rest of the second line with the default attribute:

        >>> canvas = TextCanvas([b"foobar", b"test string"], [[("bold", 3), ("red", 2)], [("blue", 4)]])
        >>> [[(a, text) for a, _cs, text in row] for row in canvas.content()]
        [[('bold', b'foo'), ('red', b'ba'), (None, b'r     ')], [('blue', b'test'), (None, b' string')]]

        :param text: lines of text, encoded in the screen's encoding (see :func:`urwid.set_encoding`)
        :param attr: runs of display attributes for each line:
            palette entry names, :class:`AttrSpec` or :class:`LayeredAttr` values, or ``None`` for the default attribute
        :param cs: runs of character sets for each line:

            - ``"0"``: the DEC special graphics set, in a non-UTF-8 encoding.
            - ``"U"``: bytes written unchanged, without filtering control characters;
              in a non-UTF-8 encoding, also the IBM PC character set.
            - ``None``: the default set.
        :param cursor: (x,y) of cursor or None
        :param maxcol: screen columns taken by this canvas
        :param check_width: check and fix width of all lines in text
        :raises CanvasError: a line of *text* is not a plain string in the screen encoding, is wider than *maxcol*, or
            has an attribute or character set run extending beyond its padded text.
        :raises TypeError: *maxcol* is not an integer.
        """
        super().__init__()
        if text is None:
            text = []

        if check_width:
            widths = []
            for t in text:
                if not isinstance(t, bytes):
                    raise CanvasError(
                        "Canvas text must be plain strings encoded in the screen's encoding",
                        repr(text),
                    )
                widths.append(calc_width(t, 0, len(t)))
        else:
            if not isinstance(maxcol, int):
                raise TypeError(maxcol)
            widths = [maxcol] * len(text)

        if maxcol is None:
            if widths:
                # find maxcol ourselves
                maxcol = max(widths)
            else:
                maxcol = 0

        # content() pairs each line with its runs, so a line with no list of runs would be left out of it
        attr = attr or []
        if len(attr) < len(text):
            attr = [*attr, *([] for _ in range(len(text) - len(attr)))]
        cs = cs or []
        if len(cs) < len(text):
            cs = [*cs, *([] for _ in range(len(text) - len(cs)))]

        # pad text and attr to maxcol
        for i, (w, a_row, cs_row) in enumerate(zip(widths, attr, cs, strict=False)):
            if w > maxcol:
                raise CanvasError(
                    f"Canvas text is wider than the maxcol specified:\n"
                    f"maxcol={maxcol!r}\n"
                    f"widths={widths!r}\n"
                    f"text={text!r}\n"
                    f"urwid target encoding={get_encoding()}"
                )
            t = text[i]
            if w < maxcol:
                t += b"".rjust(maxcol - w)
                text[i] = t
            a_gap = len(t) - rle_len(a_row)
            if a_gap < 0:
                raise CanvasError(f"Attribute extends beyond text \n{t!r}\n{a_row!r}")
            if a_gap:
                rle_append_modify(a_row, (None, a_gap))

            cs_gap = len(t) - rle_len(cs_row)
            if cs_gap < 0:
                raise CanvasError(f"Character Set extends beyond text \n{t!r}\n{cs_row!r}")
            if cs_gap:
                rle_append_modify(cs_row, (None, cs_gap))

        self._attr = attr
        self._cs = cs
        self.cursor = cursor
        self._text = text
        self._maxcol = maxcol

    def rows(self) -> int:
        """Return the number of rows in this canvas."""
        return len(self._text)

    def cols(self) -> int:
        """Return the screen column width of this canvas."""
        return self._maxcol

    def translated_coords(self, dx: int, dy: int) -> tuple[int, int] | None:
        """Return cursor coords shifted by (dx, dy), or None if there is no cursor."""
        if self.cursor:
            x, y = self.cursor
            return x + dx, y + dy
        return None

    def content(
        self,
        trim_left: int = 0,
        trim_top: int = 0,
        cols: int = 0,
        rows: int = 0,
        attr: Mapping[Hashable, Hashable] | None = None,
    ) -> Iterator[_ContentLine]:
        """Return the canvas content as a list of rows where each row is a list of (attr, cs, text) tuples.

        trim_left, trim_top, cols, rows may be set by
        CompositeCanvas when rendering a partially obscured
        canvas.

        :raises ValueError: *trim_left* or *trim_top*, together with *cols* or *rows*, selects a region outside this
            canvas.
        """
        maxcol, maxrow = self.cols(), self.rows()
        if not cols:
            cols = maxcol - trim_left
        if not rows:
            rows = maxrow - trim_top

        # a canvas without columns (empty text) has one region only: all of it, zero columns wide
        if not (
            (0 <= trim_left < maxcol and cols > 0 and trim_left + cols <= maxcol) or maxcol == trim_left == cols == 0
        ):
            raise ValueError(trim_left)
        if not ((0 <= trim_top < maxrow) and (rows > 0 and trim_top + rows <= maxrow)):
            raise ValueError(trim_top)

        if trim_top or rows < maxrow:
            text_attr_cs = zip(
                self._text[trim_top : trim_top + rows],
                self._attr[trim_top : trim_top + rows],
                self._cs[trim_top : trim_top + rows],
                strict=False,
            )
        else:
            text_attr_cs = zip(self._text, self._attr, self._cs, strict=False)

        for text, a_row, cs_row in text_attr_cs:
            if trim_left or cols < self._maxcol:
                # each row is replaced by its trimmed form before the attributes are combined below
                text, a_row, cs_row = trim_text_attr_cs(  # noqa: PLW2901
                    text,
                    a_row,
                    cs_row,
                    trim_left,
                    trim_left + cols,
                )

            attr_cs = rle_product(a_row, cs_row)
            i = 0
            row = []
            for (a, cs), run in attr_cs:
                if attr:
                    a = attr.get(a, a)  # noqa: PLW2901  # single lookup instead of `in` + `[]`
                row.append((a, cs, text[i : i + run]))
                i += run
            yield row


# C0 and C1 control characters and DEL, other than TAB and LF, which the layout places,
# and SO and SI, which select the DEC line-drawing character set
_CONTROL_CHARS = "\x00-\x08\x0b-\x0d\x10-\x1f\x7f-\x9f"
_CONTROL_RE = re.compile(f"[{_CONTROL_CHARS}]")
_CONTROL_UTF8_RE = re.compile(rb"[\x00-\x08\x0b-\x0d\x10-\x1f\x7f]|\xc2[\x80-\x9f]")
_DRAWN_RUN_RE = re.compile(f"[^{_CONTROL_CHARS}]+")


def _drawn_ranges(text: str | bytes, start: int, end: int, sc: int) -> list[tuple[int, int]] | None:
    """Return the ranges of text[start:end] to draw so that they take the *sc* screen columns the layout measured.

    The layout measures a segment either with :func:`calc_width`, which takes every escape sequence and control
    character as zero columns, or with :func:`calc_text_pos`, which takes the control characters as zero columns
    and the rest of an escape sequence, such as ``[31m`` after ESC, as printable text.
    Leaving out what the measure that gives *sc* takes as zero columns draws exactly *sc* columns,
    and nothing reaches the display for it to draw as ``?`` or to run as a terminal command.

    :returns: ``None`` to draw the segment unchanged: it has no control character,
        it is a byte string in an encoding that measures every byte as one column, or neither measure gives *sc*.
    """
    if isinstance(text, bytes):
        if get_byte_encoding() != "utf8" or not _CONTROL_UTF8_RE.search(text, start, end):
            return None
        try:
            decoded = text[start:end].decode("utf-8")
        except UnicodeDecodeError:
            return None
        offsets: Sequence[int] = list(
            itertools.accumulate((len(char.encode("utf-8")) for char in decoded), initial=start)
        )
    else:
        if not _CONTROL_RE.search(text, start, end):
            return None
        decoded = text[start:end]
        offsets = range(start, end + 1)

    whole: list[tuple[int, int]] = []
    pos = 0
    for part, is_sequence in wcwidth.iter_sequences(decoded):
        # calc_width keeps the text a sequence displays, such as that of OSC 66 text sizing
        kept = wcwidth.strip_sequences(part) if is_sequence else part
        at = pos + part.rfind(kept)
        whole.extend((at + found.start(), at + found.end()) for found in _DRAWN_RUN_RE.finditer(kept))
        pos += len(part)
    controls_only = [found.span() for found in _DRAWN_RUN_RE.finditer(decoded)]
    for ranges in (whole, controls_only):
        drawn = "".join(decoded[s:e] for s, e in ranges)
        if calc_width(drawn, 0, len(drawn)) == sc:
            return [(offsets[s], offsets[e]) for s, e in ranges]
    return None


@dataclasses.dataclass(slots=True, weakref_slot=True)
class _AttrWalk:
    counter: int = 0  # counter for moving through elements of a
    offset: int = 0  # current offset into text of attr[ak]


def apply_text_layout(
    text: str | bytes,
    attr: Sequence[tuple[Hashable, int]],
    ls: Iterable[list[tuple[int, int, int | bytes] | tuple[int, int | None]]],
    maxcol: int,
) -> TextCanvas:
    """Build a :class:`TextCanvas` by encoding *text* and *attr* according to the line layout *ls*.

    Control characters and escape sequences that the layout measured as zero columns are left out of the canvas,
    so that each line is drawn in the screen columns the layout measured.
    """
    t: list[bytes] = []
    a: list[list[tuple[Hashable, int]]] = []
    c: list[list[tuple[Literal["0", "U"] | None, int]]] = []

    aw = _AttrWalk()

    def arange(start_offs: int, end_offs: int) -> list[tuple[Hashable, int]]:
        """Return an attribute list for the range of text specified."""
        if start_offs < aw.offset:
            aw.counter = 0
            aw.offset = 0
        o: list[tuple[Hashable, int]] = []
        # the loop should run at least once, the '=' part ensures that
        while aw.offset <= end_offs:
            if len(attr) <= aw.counter:
                # run out of attributes
                o.append((None, end_offs - max(start_offs, aw.offset)))
                break
            at, run = attr[aw.counter]
            if aw.offset + run <= start_offs:
                # move forward through attr to find start_offs
                aw.counter += 1
                aw.offset += run
                continue
            if end_offs <= aw.offset + run:
                o.append((at, end_offs - max(start_offs, aw.offset)))
                break
            o.append((at, aw.offset + run - max(start_offs, aw.offset)))
            aw.counter += 1
            aw.offset += run
        return o

    # one search of the whole text spares the search of each segment for text without control characters
    has_control = bool(_CONTROL_UTF8_RE.search(text) if isinstance(text, bytes) else _CONTROL_RE.search(text))

    for line_layout in ls:
        # trim the line to fit within maxcol
        line_layout = trim_line(line_layout, text, 0, maxcol)  # noqa: PLW2901

        line = []
        linea: list[tuple[Hashable, int]] = []
        linec: list[tuple[Literal["0", "U"] | None, int]] = []

        def attrrange(
            start_offs: int,
            end_offs: int,
            destw: int,
            *,
            src: str | bytes = text,
            runs: list[tuple[Hashable, int]] | None = None,
        ) -> None:
            """Add attributes based on attributes between start_offs and end_offs.

            :param start_offs: offset into *src* where the range starts
            :param end_offs: offset into *src* where the range ends
            :param destw: number of bytes the range encodes to
            :param src: the text *start_offs* and *end_offs* index, which encodes to *destw* bytes
            :param runs: the attributes of src[start_offs:end_offs], ``None`` to look them up in *attr*
            """
            # pylint: disable=cell-var-from-loop
            if start_offs == end_offs:
                [(at, run)] = arange(start_offs, end_offs)  # pylint: disable=unbalanced-tuple-unpacking
                rle_append_modify(linea, (at, destw))  # noqa: B023
                return
            if runs is None:
                runs = arange(start_offs, end_offs)
            if destw == end_offs - start_offs:
                for at, run in runs:
                    rle_append_modify(linea, (at, run))  # noqa: B023
                return
            # encoded version has different width
            o = start_offs
            for at, run in runs:
                if o + run == end_offs:
                    rle_append_modify(linea, (at, destw))  # noqa: B023
                    return
                tseg = src[o : o + run]
                tseg, cs = apply_target_encoding(tseg)
                segw = rle_len(cs)

                rle_append_modify(linea, (at, segw))  # noqa: B023
                o += run
                destw -= segw

        for seg in line_layout:
            # if seg is None: assert 0, ls
            s = LayoutSegment(seg)
            if s.end:
                offs = typing.cast("int", s.offs)  # s.end is set
                if not has_control or (drawn := _drawn_ranges(text, offs, s.end, s.sc)) is None:
                    tseg, cs = apply_target_encoding(text[offs : s.end])
                    attrrange(offs, s.end, rle_len(cs))
                else:
                    seg_text: str | bytes
                    if isinstance(text, bytes):
                        seg_text = b"".join(text[start:end] for start, end in drawn)
                    else:
                        seg_text = "".join(text[start:end] for start, end in drawn)
                    tseg, cs = apply_target_encoding(seg_text)
                    runs: list[tuple[Hashable, int]] = []
                    for start, end in drawn:
                        for run in arange(start, end):
                            rle_append_modify(runs, run)
                    attrrange(0, len(seg_text), rle_len(cs), src=seg_text, runs=runs)
                line.append(tseg)
                rle_join_modify(linec, cs)
            elif s.text:
                tseg, cs = apply_target_encoding(s.text)
                line.append(tseg)
                attrrange(typing.cast("int", s.offs), typing.cast("int", s.offs), len(tseg))  # s.text is set
                rle_join_modify(linec, cs)
            elif s.offs:
                if s.sc:
                    line.append(b"".rjust(s.sc))
                    attrrange(s.offs, s.offs, s.sc)
            else:
                line.append(b"".rjust(s.sc))
                linea.append((None, s.sc))
                linec.append((None, s.sc))

        t.append(b"".join(line))
        a.append(linea)
        c.append(linec)

    return TextCanvas(t, a, c, maxcol=maxcol)
