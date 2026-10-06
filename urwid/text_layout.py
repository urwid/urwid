# Urwid Text Layout classes
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


"""Text layout: wrapping and aligning text into lines of screen columns."""

from __future__ import annotations

import bisect
import functools
import typing

import wcwidth

from urwid.str_util import calc_text_pos, calc_width, is_wide_char, move_next_char, move_prev_char
from urwid.util import calc_trim_text, get_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Literal

    from urwid.widget import Align, WrapMode

    _LayoutSegment = tuple[int, int, int | bytes] | tuple[int, int | None]
    _LayoutLine = list[_LayoutSegment]
    _LayoutFormat = list[_LayoutLine]


@functools.lru_cache(maxsize=4)
def get_ellipsis_string(encoding: str) -> str:
    """Get ellipsis character for given encoding."""
    try:
        return "…".encode(encoding).decode(encoding)
    except UnicodeEncodeError:
        return "..."


@functools.lru_cache(maxsize=4)
def _get_width(string: str) -> int:
    """Get ellipsis character width for given encoding."""
    return wcwidth.width(string, control_codes="ignore")


def _calc_fitting_text(text: str | bytes, start: int, end: int, max_cols: int) -> tuple[int, int]:
    """Return the end offset and the screen columns of the longest part of text[start:end] fitting into max_cols.

    Text of up to ``4 * max_cols + 16`` code units is measured as a whole first. Longer text is cut with
    :func:`calc_text_pos` before it is measured, so the cost follows the length of the part that fits
    rather than the length of the whole range.
    """
    if end - start <= 4 * max_cols + 16 and (cols := calc_width(text, start, end)) <= max_cols:
        return end, cols
    pos, cols = calc_text_pos(text, start, end, max_cols)
    if pos == end and (whole := calc_width(text, start, end)) <= max_cols:
        # the per-cluster measure of calc_text_pos and the whole-text measure of calc_width can disagree
        cols = whole
    return pos, cols


class TextLayout:
    """Base class for a text layout algorithm that lays text out into lines for display."""

    def supports_align_mode(self, align: Literal["left", "center", "right"] | Align) -> bool:
        """Return True if align is a supported align mode."""
        return True

    def supports_wrap_mode(self, wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode) -> bool:
        """Return True if wrap is a supported wrap mode."""
        return True

    def layout(
        self,
        text: str | bytes,
        width: int,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode,
    ) -> _LayoutFormat:
        """
        Return a layout structure for text.

        :param text: string in current encoding or unicode string
        :param width: number of screen columns available
        :param align: align mode for text
        :param wrap: wrap mode for text
        :raises NotImplementedError: the subclass does not provide a layout implementation.

        Layout structure is a list of line layouts, one per output line.
        Line layouts are lists than may contain the following tuples:

        * (column width of text segment, start offset, end offset)
        * (number of space characters to insert, offset or None)
        * (column width of insert text, offset, "insert text")

        The offset in the last two tuples is used to determine the
        attribute used for the inserted spaces or text respectively.
        The attribute used will be the same as the attribute at that
        text offset.  If the offset is None when inserting spaces
        then no attribute will be used.
        """
        raise NotImplementedError(
            "This function must be overridden by a real text layout class. (see StandardTextLayout)"
        )


class CanNotDisplayText(Exception):
    """Raised internally by a text layout when the given text cannot be laid out at all."""


class StandardTextLayout(TextLayout):
    """Default :class:`TextLayout` implementation, wrapping and aligning text by screen column."""

    def __init__(
        self,
        *,
        tab_stops: Iterable[int] = (),
        tab_stop_every: int = 8,
    ) -> None:
        """Create a layout with word-processor style tab stops.

        A tab character advances to the next tab stop, measured in rendered screen columns
        from the start of the displayed line: explicit *tab_stops* are used first,
        then stops repeat every *tab_stop_every* columns counted from column 0.
        With *tab_stop_every* ``0`` a tab past the last explicit stop takes no columns.

        :param tab_stops: screen columns of explicit tab stops.
        :param tab_stop_every: interval of the default tab stops, ``0`` for none.
        :raises ValueError: *tab_stop_every* is negative, or one of *tab_stops* is not a positive column.
        """
        self.tab_stops: tuple[int, ...] = tuple(sorted(set(tab_stops)))
        if tab_stop_every < 0 or (self.tab_stops and self.tab_stops[0] < 1):
            raise ValueError(f"Tab stops must be positive: {tab_stops=!r}, {tab_stop_every=!r}")
        self.tab_stop_every = tab_stop_every

    def next_tab_stop(self, column: int) -> int:
        """Return the screen column of the first tab stop after *column*.

        When there is no stop after *column*, return *column* itself: the tab takes no columns.

        >>> StandardTextLayout(tab_stops=(4, 10)).next_tab_stop(5)
        10
        >>> StandardTextLayout(tab_stops=(4, 10)).next_tab_stop(10)
        16
        >>> StandardTextLayout(tab_stops=(4, 10), tab_stop_every=0).next_tab_stop(10)
        10
        """
        if (idx := bisect.bisect_right(self.tab_stops, column)) < len(self.tab_stops):
            return self.tab_stops[idx]
        if not self.tab_stop_every:
            return column
        return (column // self.tab_stop_every + 1) * self.tab_stop_every

    def supports_align_mode(self, align: Literal["left", "center", "right"] | Align) -> bool:
        """Return True if align is 'left', 'center' or 'right'."""
        return align in {"left", "center", "right"}

    def supports_wrap_mode(self, wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode) -> bool:
        """Return True if wrap is 'any', 'space', 'clip' or 'ellipsis'."""
        return wrap in {"any", "space", "clip", "ellipsis"}

    def layout(
        self,
        text: str | bytes,
        width: int,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode,
    ) -> _LayoutFormat:
        """Return a layout structure for text."""
        try:
            segs = self.calculate_text_segments(text, width, wrap)
            return self.align_layout(text, width, segs, wrap, align)  # type: ignore[arg-type]  # segs is narrowed
        except CanNotDisplayText:
            return [[]]

    def pack(
        self,
        maxcol: int,
        layout: _LayoutFormat,
    ) -> int:
        """Return a minimal maxcol value that would result in the same number of lines for layout.

        layout must be a layout structure returned by self.layout().

        :raises ValueError: *layout* is empty.
        """
        maxwidth = 0
        if not layout:
            raise ValueError(f"huh? empty layout?: {layout!r}")
        for lines in layout:
            lw = line_width(lines)
            if lw >= maxcol:
                return maxcol
            maxwidth = max(maxwidth, lw)
        return maxwidth

    def align_layout(
        self,
        text: str | bytes,
        width: int,
        segs: _LayoutFormat,
        wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode,
        align: Literal["left", "center", "right"] | Align,
    ) -> _LayoutFormat:
        """Convert the layout segments to an aligned layout.

        :raises ValueError: *align* is not a supported alignment.
        """
        out = []
        for lines in segs:
            sc = line_width(lines)
            if sc == width or align == "left":
                out.append(lines)
                continue

            if align == "right":
                out.append([(width - sc, None), *lines])
                continue
            if align != "center":
                raise ValueError(align)
            pad_trim_left = (width - sc + 1) // 2
            out.append([(pad_trim_left, None), *lines] if pad_trim_left else lines)
        return out

    def _calculate_trimmed_segments(
        self,
        text: str | bytes,
        width: int,
        wrap: Literal["clip", "ellipsis", WrapMode.CLIP, WrapMode.ELLIPSIS],
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int]]]:
        """Calculate text segments for cases of a text trimmed (wrap is clip or ellipsis).

        :raises ValueError: the computed padding or start offset contradicts a start column of ``0``.
        """
        segments = []

        nl: str | bytes = "\n" if isinstance(text, str) else b"\n"
        tab: str | bytes = "\t" if isinstance(text, str) else b"\t"
        encoding = get_encoding()
        ellipsis_string = get_ellipsis_string(encoding)
        ellipsis_width = _get_width(ellipsis_string)
        if (extra := width - ellipsis_width - 1) < 0:
            ellipsis_string = ellipsis_string[:extra]
            ellipsis_width = _get_width(ellipsis_string)

        ellipsis_char = ellipsis_string.encode(encoding)

        idx = 0

        while idx <= len(text):
            nl_pos = text.find(nl, idx)  # type: ignore[arg-type]  # We normalise types
            if nl_pos == -1:
                nl_pos = len(text)
            if text.find(tab, idx, nl_pos) != -1:  # type: ignore[arg-type]  # We normalise types
                tabbed_line, screen_columns, end_off = self._place_tabbed_line(text, idx, nl_pos)
                if wrap == "ellipsis" and screen_columns > width and ellipsis_width:
                    limit = width - ellipsis_width
                    tabbed_line, screen_columns, end_off = self._place_tabbed_line(text, idx, nl_pos, limit=limit)
                    tabbed_line += [(ellipsis_width, end_off, ellipsis_char), (limit - screen_columns, end_off)]
                else:
                    tabbed_line += [(0, nl_pos)]
                segments.append(tabbed_line)
                idx = nl_pos + 1
                continue

            screen_columns = calc_width(text, idx, nl_pos)

            # trim line to max width if needed, add ellipsis if trimmed
            if wrap == "ellipsis" and screen_columns > width and ellipsis_width:
                trimmed = True

                start_off, end_off, pad_left, pad_right = calc_trim_text(text, idx, nl_pos, 0, width - ellipsis_width)
                # pad_left should be 0, because the start_col parameter was 0 (no trimming on the left)
                # similarly spos should not be changed from p
                if pad_left != 0:
                    raise ValueError(f"Invalid padding for start column==0: {pad_left!r}")
                if start_off != idx:
                    raise ValueError(f"Invalid start offset for  start column==0 and position={idx!r}: {start_off!r}")
                screen_columns = width - ellipsis_width - pad_right

            else:
                trimmed = False
                end_off = nl_pos
                pad_right = 0

            line: list[tuple[int, int, int | bytes] | tuple[int, int]] = []
            if idx != end_off and screen_columns:
                line += [(screen_columns, idx, end_off)]
            if trimmed:
                line += [(ellipsis_width, end_off, ellipsis_char)]
            line += [(pad_right, end_off)]
            segments.append(line)
            idx = nl_pos + 1
        return segments

    def _place_tabbed_line(
        self,
        text: str | bytes,
        start: int,
        end: int,
        *,
        limit: int | None = None,
    ) -> tuple[list[tuple[int, int, int | bytes] | tuple[int, int]], int, int]:
        """Lay out one line holding tab characters without wrapping it.

        :param limit: screen columns to stop at, ``None`` to lay out the whole line.
        :returns: the line segments, their total screen columns,
            and the text offset the layout stopped at (*end* unless *limit* cut the line short).
        """
        tab: str | bytes = "\t" if isinstance(text, str) else b"\t"
        line: list[tuple[int, int, int | bytes] | tuple[int, int]] = []
        column = 0
        pos = start
        while pos < end:
            if text[pos : pos + 1] == tab:
                if not (tab_width := self.next_tab_stop(column) - column):
                    line.append((0, pos))
                    pos += 1
                    continue
                if limit is not None and column + tab_width > limit:
                    if limit > column:
                        line.append((limit - column, pos, b" " * (limit - column)))
                    return line, limit, pos
                line.append((tab_width, pos, b" " * tab_width))
                column += tab_width
                pos += 1
                continue

            if (chunk_end := text.find(tab, pos, end)) == -1:  # type: ignore[arg-type]  # same type as text
                chunk_end = end
            chunk_width = calc_width(text, pos, chunk_end)
            if limit is not None and column + chunk_width > limit:
                _, epos, _, pad_right = calc_trim_text(text, pos, chunk_end, 0, limit - column)
                if (fitted := limit - column - pad_right) > 0:
                    line.append((fitted, pos, epos))
                return line, limit - pad_right, epos
            if chunk_width:
                line.append((chunk_width, pos, chunk_end))
            column += chunk_width
            pos = chunk_end
        return line, column, end

    def _wrap_tabbed_line(
        self,
        text: str | bytes,
        start: int,
        end: int,
        width: int,
        wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int]]]:
        """Wrap one line holding tab characters into display lines of *width* screen columns.

        Tab stops restart at column 0 on every display line. A tab reaching past *width* is cut at the line end,
        and in ``space`` mode it is also a break opportunity, like a space.

        :raises CanNotDisplayText: a character does not fit into an empty display line.
        :raises ValueError: *wrap* is not a supported wrapping mode.
        """
        if wrap not in {"any", "space"}:
            raise ValueError(wrap)
        tab: str | bytes = "\t" if isinstance(text, str) else b"\t"
        space: str | bytes = " " if isinstance(text, str) else b" "
        lines: list[list[tuple[int, int, int | bytes] | tuple[int, int]]] = []
        line: list[tuple[int, int, int | bytes] | tuple[int, int]] = []
        column = 0
        pos = start
        chunk_end = start - 1
        while pos < end:
            if text[pos : pos + 1] == tab:
                if self.next_tab_stop(column) == column:
                    line.append((0, pos))
                    pos += 1
                elif column < width:
                    tab_width = min(self.next_tab_stop(column), width) - column
                    line.append((tab_width, pos, b" " * tab_width))
                    column += tab_width
                    pos += 1
                elif not column:
                    raise CanNotDisplayText("Tab will not fit in 0-column width")
                elif wrap == "space":
                    # the tab at the line end is the break itself: drop it, as a space is dropped
                    lines.append([*line, (0, pos)])
                    line, column, pos = [], 0, pos + 1
                else:
                    lines.append(line)
                    line, column = [], 0
                continue

            # the tab found for an earlier display line still ends the chunk this one continues
            if chunk_end < pos and (chunk_end := text.find(tab, pos, end)) == -1:  # type: ignore[arg-type]
                chunk_end = end
            if (
                chunk_end - pos <= width - column
                and column + (chunk_width := calc_width(text, pos, chunk_end)) <= width
            ):
                brk = chunk_end
            else:
                brk, chunk_width = _calc_fitting_text(text, pos, chunk_end, width - column)
            if brk == chunk_end:
                if chunk_width:
                    line.append((chunk_width, pos, chunk_end))
                column += chunk_width
                pos = chunk_end
                continue

            cut: int | None = None
            resume = brk
            if wrap == "any":
                if brk > pos:
                    cut = brk
            elif text[brk : brk + 1] == space:
                cut, resume = brk, brk + 1
            elif brk > pos and is_wide_char(text, brk):
                cut = brk
            else:
                prev = brk
                while prev > pos:
                    prev = move_prev_char(text, pos, prev)
                    if text[prev : prev + 1] == space:
                        cut, resume = prev, prev + 1
                        break
                    if is_wide_char(text, prev):
                        cut = resume = move_next_char(text, prev, brk)
                        break

            if cut is None:
                if not column:
                    if brk == pos:
                        raise CanNotDisplayText("Wide character will not fit in 1-column width")
                    # no break opportunity at all: force a character wrap
                    cut = brk
                else:
                    # break right after the preceding tab
                    lines.append(line)
                    line, column = [], 0
                    continue

            if cut > pos and (chunk_width := calc_width(text, pos, cut)):
                line.append((chunk_width, pos, cut))
            if resume > cut:
                line.append((0, cut))  # removed character hint
            lines.append(line)
            line, column, pos = [], 0, resume

        lines.append([*line, (0, end)])  # removed character hint
        return lines

    def calculate_text_segments(
        self,
        text: str | bytes,
        width: int,
        wrap: Literal["any", "space", "clip", "ellipsis"] | WrapMode,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int]]]:
        """
        Calculate the segments of text to display given width screen columns to display them.

        text - Unicode text or byte string to display
        width - number of available screen columns
        wrap - wrapping mode used

        Returns a layout structure without an alignment applied.
        Each line holding a tab character is laid out with tab stops, see :meth:`next_tab_stop`::

            wrap is clip or ellipsis? --yes--> per line: tabs? --yes--> place tabs, then cut with ellipsis
                    |                                    +--no---> cut with ellipsis
                    no
                    |
            per line: tabs? --yes--> wrap tab by tab
                      +--no---> wrap at spaces or anywhere

        :raises CanNotDisplayText: a character does not fit into an empty display line.
        :raises ValueError: *wrap* is not a supported wrapping mode.
        """
        if wrap in {"clip", "ellipsis"}:
            return self._calculate_trimmed_segments(text, width, wrap)  # type: ignore[arg-type]  # filtered by if

        nl: str | bytes
        tab: str | bytes
        nl_o: int | str
        sp_o: int | str
        nl, tab, nl_o, sp_o = "\n", "\t", "\n", " "
        if isinstance(text, bytes):
            nl = b"\n"  # can only find bytes in python3 bytestrings
            tab = b"\t"
            nl_o = ord(nl_o)  # + an item of a bytestring is the ordinal value
            sp_o = ord(sp_o)

        segments: list[list[tuple[int, int, int | bytes] | tuple[int, int]]] = []
        idx = 0
        nl_pos = -1

        while idx <= len(text):
            if nl_pos < idx:
                # look for the next eligible line break, valid until idx passes it
                nl_pos = text.find(nl, idx)  # type: ignore[arg-type]  # We normalise types
                if nl_pos == -1:
                    nl_pos = len(text)

                if text.find(tab, idx, nl_pos) != -1:  # type: ignore[arg-type]  # We normalise types
                    segments.extend(self._wrap_tabbed_line(text, idx, nl_pos, width, wrap))
                    idx = nl_pos + 1
                    continue

            if nl_pos - idx <= width and (screen_columns := calc_width(text, idx, nl_pos)) <= width:
                pos = nl_pos
            else:
                pos, screen_columns = _calc_fitting_text(text, idx, nl_pos, width)
            if pos == nl_pos:
                if screen_columns:
                    # this segment fits
                    segments.append([(screen_columns, idx, nl_pos), (0, nl_pos)])
                else:
                    segments.append([(0, nl_pos)])
                # removed character hint
                idx = nl_pos + 1
                continue

            if pos == idx:  # pathological width=1 double-byte case
                raise CanNotDisplayText("Wide character will not fit in 1-column width")

            if wrap == "any":
                segments.append([(screen_columns, idx, pos)])
                idx = pos
                continue

            if wrap != "space":
                raise ValueError(wrap)

            if text[pos] == sp_o:
                # perfect space wrap
                segments.append([(screen_columns, idx, pos), (0, pos)])
                # removed character hint

                idx = pos + 1
                continue

            if is_wide_char(text, pos):
                # perfect next wide
                segments.append([(screen_columns, idx, pos)])
                idx = pos
                continue

            prev = pos
            while prev > idx:
                prev = move_prev_char(text, idx, prev)
                if text[prev] == sp_o:
                    screen_columns = calc_width(text, idx, prev)
                    line: list[tuple[int, int, int | bytes] | tuple[int, int]] = [(0, prev)]
                    if screen_columns:
                        line = [(screen_columns, idx, prev), *line]
                    segments.append(line)
                    idx = prev + 1
                    break

                if is_wide_char(text, prev):
                    # wrap after wide char
                    next_char = move_next_char(text, prev, pos)
                    screen_columns = calc_width(text, idx, next_char)
                    segments.append([(screen_columns, idx, next_char)])
                    idx = next_char
                    break

            else:
                # unwrap previous line space if possible to
                # fit more text (we're breaking a word anyway)
                if segments and (len(segments[-1]) == 2 or (len(segments[-1]) == 1 and len(segments[-1][0]) == 2)):
                    # look for the removed space above
                    if len(segments[-1]) == 1:
                        [(h_sc, h_off)] = segments[-1]  # type: ignore[misc]  # we filtered-out case
                        p_sc = 0
                        p_off = _p_end = h_off

                    else:
                        [(p_sc, p_off, _p_end), (h_sc, h_off)] = segments[-1]  # type: ignore[misc]

                    if (
                        p_sc < width
                        and h_sc == 0
                        and text[h_off] == sp_o
                        # a join that breaks before the removed space again would repeat this line forever
                        and (joined := calc_text_pos(text, p_off, nl_pos, width))[0] > h_off
                    ):
                        # combine with the previous line
                        del segments[-1]
                        idx = p_off
                        pos, screen_columns = joined
                        segments.append([(screen_columns, idx, pos)])
                        # check for trailing " " or "\n"
                        idx = pos
                        if idx < len(text) and (text[idx] in {sp_o, nl_o}):
                            # removed character hint
                            segments[-1].append((0, idx))
                            idx += 1
                        continue

                # force any char wrap
                segments.append([(screen_columns, idx, pos)])
                idx = pos
        return segments


######################################
# default layout object to use
default_layout = StandardTextLayout()
######################################


class LayoutSegment:
    """One segment of a line layout: a run of text, an inserted range of spaces, or inserted text."""

    __slots__ = ("end", "offs", "sc", "text")

    sc: int
    offs: int | None
    text: bytes | None
    end: int | None

    def __init__(self, seg: _LayoutSegment) -> None:
        """Create object from line layout segment structure.

        :raises TypeError: *seg* is not a tuple, or one of its members has the wrong type.
        :raises ValueError: *seg* does not have 2 or 3 members, or holds an out-of-range screen column count.
        """
        if not isinstance(seg, tuple):
            raise TypeError(seg)

        # Unpacking in one step instead of slicing and re-indexing: this runs once per layout segment
        # of every rendered line.
        if len(seg) == 3:
            self.sc, self.offs, t = seg
            if not isinstance(self.sc, int):
                raise TypeError(self.sc)
            if not isinstance(self.offs, int):
                raise TypeError(self.offs)
            if self.sc <= 0:
                raise ValueError(seg)
            if isinstance(t, bytes):
                self.text = t
                self.end = None
            else:
                if not isinstance(t, int):
                    raise TypeError(t)
                self.text = None
                self.end = t
        elif len(seg) == 2:
            self.sc, self.offs = seg
            if not isinstance(self.sc, int):
                raise TypeError(self.sc)
            if self.offs is not None:
                if self.sc < 0:
                    raise ValueError(seg)
                if not isinstance(self.offs, int):
                    raise TypeError(self.offs)
            self.text = self.end = None
        else:
            raise ValueError(seg)

    def subseg(
        self,
        text: str | bytes,
        start: int,
        end: int,
    ) -> _LayoutLine:
        """
        Return a "sub-segment" list containing segment structures that make up a portion of this segment.

        A list is returned to handle cases where wide characters
        need to be replaced with a space character at either edge
        so two or three segments will be returned.

        :raises ValueError: this segment carries text or an end offset but no text offset.
        """
        start = max(start, 0)
        end = min(end, self.sc)

        if start >= end:
            return []  # completely gone

        if self.text or self.end:
            if self.offs is None:
                raise ValueError("offs cannot be None when text or end is present")

            if self.text:
                # use text stored in segment (self.text)
                spos, epos, pad_left, pad_right = calc_trim_text(self.text, 0, len(self.text), start, end)
                return [
                    (
                        end - start,
                        self.offs,
                        b"".ljust(pad_left) + self.text[spos:epos] + b"".ljust(pad_right),
                    )
                ]
            if self.end:
                # use text passed as parameter (text)
                spos, epos, pad_left, pad_right = calc_trim_text(text, self.offs, self.end, start, end)
                lines: list[tuple[int, int, int] | tuple[int, int]] = []
                if pad_left:
                    lines.append((1, move_prev_char(text, self.offs, spos)))
                # A window that both starts and ends inside wide characters has
                # nothing left between the two padding cells, and a segment of
                # zero screen columns is not a shape LayoutSegment accepts.
                if (seg_cols := end - start - pad_left - pad_right) > 0:
                    lines.append((seg_cols, spos, epos))
                if pad_right:
                    lines.append((1, epos))
                return lines  # type: ignore[return-value]  # we're narrowing return type

        return [(end - start, self.offs)]


def line_width(segs: _LayoutLine) -> int:
    """
    Return the screen column width of one line of a text layout structure.

    This function ignores any existing shift applied to the line,
    represented by an (amount, None) tuple at the start of the line.
    """
    sc = 0
    seglist = segs
    if segs and len(segs[0]) == 2 and segs[0][1] is None:
        seglist = segs[1:]
    for s in seglist:
        sc += s[0]
    return sc


def shift_line(
    segs: _LayoutLine,
    amount: int,
) -> _LayoutLine:
    """
    Return a shifted line from a layout structure to the left or right.

    :param segs: line of a layout structure
    :param amount: screen columns to shift right (+ve) or left (-ve)
    :raises TypeError: *amount* is not an integer.
    """
    if not isinstance(amount, int):
        raise TypeError(amount)

    if segs and len(segs[0]) == 2 and segs[0][1] is None:
        # existing shift
        amount += segs[0][0]
        if amount:
            return [(amount, None), *segs[1:]]
        return segs[1:]

    if amount:
        return [(amount, None), *segs]
    return segs


def trim_line(
    segs: _LayoutLine,
    text: str | bytes,
    start: int,
    end: int,
) -> _LayoutLine:
    """
    Return a trimmed line of a text layout structure.

    :param text: text to which this layout structure applies
    :param start: starting screen column
    :param end: ending screen column
    """
    result = []
    x = 0
    for seg in segs:
        sc = seg[0]
        if start or sc < 0:
            if start >= sc:
                start -= sc
                x += sc
                continue
            s = LayoutSegment(seg)
            if x + sc >= end:
                # can all be done at once
                return s.subseg(text, start, end - x)
            result += s.subseg(text, start, sc)
            start = 0
            x += sc
            continue
        if x >= end:
            break
        if x + sc > end:
            s = LayoutSegment(seg)
            result += s.subseg(text, 0, end - x)
            break
        result.append(seg)
        x += sc
    return result


def _calc_literal_line_pos(
    text: str | bytes,
    line_layout: _LayoutLine,
    pref_col: Literal["left", "right", Align.LEFT, Align.RIGHT],
) -> int | None:
    """
    Return the text position closest to *pref_col* on a line laid out without wrapping.

    :raises ValueError: *pref_col* is neither an integer nor ``'left'``/``'right'``.
    """
    if pref_col == "left":
        for seg in line_layout:
            layout = LayoutSegment(seg)
            if layout.offs is not None:
                return layout.offs
        return None

    if pref_col == "right":
        found = None
        for seg in line_layout:
            s = LayoutSegment(seg)
            if s.offs is not None:
                found = s

        if found is None:
            return None

        if found.end is None:
            return found.offs

        return calc_text_pos(
            text,
            found.offs,  # type: ignore[arg-type]  # filtered by if in lookup cycle
            found.end,
            found.sc - 1,
        )[0]

    raise ValueError(f"Invalid pref_col value: {pref_col}")


def calc_line_pos(
    text: str | bytes,
    line_layout: _LayoutLine,
    pref_col: Literal["left", "right", Align.LEFT, Align.RIGHT] | int,
) -> int | None:
    """Calculate the closest linear position to pref_col given a line layout structure.

    Returns None if no position found.

    :raises TypeError: *pref_col* is neither an integer nor ``'left'``/``'right'``.
    """
    if pref_col in {"left", "right"}:
        return _calc_literal_line_pos(text, line_layout, pref_col)

    if not isinstance(pref_col, int):
        raise TypeError(f"Invalid pref_col value: {pref_col}")

    closest_sc = None
    closest_pos: LayoutSegment | int | None = None
    current_sc = 0

    for seg in line_layout:
        s = LayoutSegment(seg)
        if s.offs is not None:
            if s.end is not None:
                if current_sc <= pref_col < current_sc + s.sc:
                    # exact match within this segment
                    return calc_text_pos(text, s.offs, s.end, pref_col - current_sc)[0]
                if current_sc <= pref_col:
                    closest_sc = current_sc + s.sc - 1
                    closest_pos = s

            if closest_sc is None or (abs(pref_col - current_sc) < abs(pref_col - closest_sc)):
                # this screen column is closer
                closest_sc = current_sc
                closest_pos = s.offs
            if current_sc > closest_sc:
                # we're moving past
                break
        current_sc += s.sc

    if closest_pos is None or isinstance(closest_pos, int):
        return closest_pos

    # return the last positions in the segment "closest_pos"
    s = closest_pos
    return calc_text_pos(text, s.offs, s.end, s.sc - 1)[0]  # type: ignore[arg-type]  # s.offs and s.end are set


def calc_pos(
    text: str | bytes,
    layout: _LayoutFormat,
    pref_col: Literal["left", "right", Align.LEFT, Align.RIGHT] | int,
    row: int,
) -> int:
    """Calculate the closest linear position to pref_col and row given a layout structure.

    :raises ValueError: *row* is outside the rows of *layout*.
    """
    if row < 0 or row >= len(layout):
        raise ValueError("calculate_pos: out of layout row range")

    if (pos := calc_line_pos(text, layout[row], pref_col)) is not None:
        return pos

    rows_above = list(range(row - 1, -1, -1))
    rows_below = list(range(row + 1, len(layout)))
    while rows_above and rows_below:
        if rows_above:
            r = rows_above.pop(0)
            if (pos := calc_line_pos(text, layout[r], pref_col)) is not None:
                return pos

        if rows_below:
            r = rows_below.pop(0)
            if (pos := calc_line_pos(text, layout[r], pref_col)) is not None:
                return pos

    return 0


def calc_coords(
    text: str | bytes,
    layout: _LayoutFormat,
    pos: int,
    clamp: int = 1,
) -> tuple[int, int]:
    """
    Calculate the coordinates closest to position pos in text with layout.

    :param text: raw string or unicode string
    :param layout: layout structure applied to text
    :param pos: integer position into text
    :param clamp: ignored right now
    """
    closest: tuple[int, tuple[int, int]] | None = None
    y = 0
    for line_layout in layout:
        x = 0
        for seg in line_layout:
            s = LayoutSegment(seg)
            if s.offs is None:
                x += s.sc
                continue
            if s.offs == pos:
                return x, y
            if s.end is not None and s.offs <= pos < s.end:
                x += calc_width(text, s.offs, pos)
                return x, y
            distance = abs(s.offs - pos)
            if s.end is not None and s.end < pos:
                distance = pos - (s.end - 1)
            if closest is None or distance < closest[0]:  # pylint: disable=unsubscriptable-object
                closest = distance, (x, y)
            x += s.sc
        y += 1

    if closest:
        return closest[1]
    return 0, 0
