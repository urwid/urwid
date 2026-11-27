"""Layout and rendering layer of :class:`Edit`."""

from __future__ import annotations

import contextlib
import typing

from urwid import text_layout
from urwid.canvas import CompositeCanvas, apply_text_layout
from urwid.str_util import calc_width, move_next_char
from urwid.util import LayeredAttr, rle_len

from ..constants import Align, MouseButton, WrapMode
from ._undo import _EditUndo

if typing.TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import Literal

    from urwid.canvas import TextCanvas


class _EditRender(_EditUndo):
    """Layout, cursor coordinates, mouse and rendering of :class:`Edit`."""

    _select_attr: Hashable | None
    _shift_view_to_cursor: bool

    #: Whether a drag with mouse button 1 selects text into :attr:`highlight`, see :meth:`mouse_event`.
    mouse_select: bool

    ignore_focus = False

    @property
    def select_attr(self) -> Hashable | None:
        """Display attribute the :attr:`highlight` range is drawn with, or ``None`` to draw it like the rest.

        It is placed over the attribute of each run under the range, as by :meth:`LayeredAttr.layer`.
        An attribute that inherits the foreground keeps the colours of :attr:`highlighter` under it,
        and one with its own foreground replaces them.
        It also draws the unfinished range of a :attr:`mouse_select` drag, and a range the application sets.
        It is not drawn over the :attr:`placeholder`; over a masked text it is drawn over the mask characters.
        Setting it redraws the widget.
        """
        return self._select_attr

    @select_attr.setter
    def select_attr(self, select_attr: Hashable | None) -> None:
        self._select_attr = select_attr
        self._invalidate()

    def get_pref_col(self, size: tuple[int]) -> int:
        r"""Return the preferred column for the cursor, or the current cursor x value.

        May also return ``'left'`` or ``'right'`` to indicate the leftmost or rightmost column available.

        This method is used internally and by other widgets when
        moving the cursor up or down between widgets so that the
        column selected is one that the user would expect.

        >>> from urwid import Edit
        >>> size = (10,)
        >>> Edit().get_pref_col(size)
        0
        >>> e = Edit("", "word")
        >>> e.get_pref_col(size)
        4
        >>> e.keypress(size, "left")
        >>> e.get_pref_col(size)
        3
        >>> e.keypress(size, "end")
        >>> e.get_pref_col(size)
        <Align.RIGHT: 'right'>
        >>> e = Edit("", "2\nwords")
        >>> e.keypress(size, "left")
        >>> e.keypress(size, "up")
        >>> e.get_pref_col(size)
        4
        >>> e.keypress(size, "left")
        >>> e.get_pref_col(size)
        0
        """
        (maxcol,) = size
        pref_col, then_maxcol = self.pref_col_maxcol
        if then_maxcol != maxcol:
            coords = self.get_cursor_coords((maxcol,))
            return coords[0] if coords is not None else 0

        return typing.cast("int", pref_col)

    def move_cursor_to_coords(
        self,
        size: tuple[int],
        x: int | Literal[Align.LEFT, Align.RIGHT],
        y: int,
    ) -> bool:
        r"""Set the cursor position with (x,y) coordinates.

        :returns: True if move succeeded, False otherwise.

        >>> from urwid import Edit
        >>> size = (10,)
        >>> e = Edit("", "edit\ntext")
        >>> e.move_cursor_to_coords(size, 5, 0)
        True
        >>> e.edit_pos
        4
        >>> e.move_cursor_to_coords(size, 5, 3)
        False
        >>> e.move_cursor_to_coords(size, 0, 1)
        True
        >>> e.edit_pos
        5
        """
        (maxcol,) = size
        trans = self.get_line_translation(maxcol)
        _top_x, top_y = self.position_coords(maxcol, 0)
        if y < top_y or y >= len(trans):
            return False

        pos = text_layout.calc_pos(self._displayed_text(), trans, x, y)
        e_pos = min(max(pos - len(self.caption), 0), len(self.edit_text))
        self.set_edit_pos(e_pos)
        self.pref_col_maxcol = x, maxcol
        self._invalidate()
        return True

    def mouse_event(
        self,
        size: tuple[int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """
        Move the cursor to the location clicked for button 1, and select text with :attr:`mouse_select`.

        Flow, with the value returned::

            press of any button, with any modifiers
            +- not button 1 ........................................ False
            +- not on a row of the text ............................ False, nothing recorded
            +- otherwise: move the cursor, record the press ........ True
            drag or release
            +- no press recorded, or the event of another button ... False
            +- without mouse_select
            |  +- drag: move the cursor ............................ whether it moved
            |  +- release: forget the press, move the cursor ....... whether it moved, False for button 0
            +- with mouse_select: move the cursor, rows clipped to the text
               +- drag ............................................. True
               +- release: forget the press, set highlight ......... True

        A drag or a release is handled only after a press of button 1 on this widget.
        A drag or a release of a press made over another widget does nothing.
        Modifier keys and a double or triple click do not change how an event is handled.

        With :attr:`mouse_select`, a drag selects from the character pressed to the character under the pointer,
        both included:

        - a press of button 1 on a row of the text moves the cursor, which clears :attr:`highlight`,
          and starts the drag;
        - each drag report moves the cursor, and the range so far is drawn while :attr:`highlight` stays ``None``;
          a row above or below the text is taken as the first or the last row;
        - the release, of button 1 or of :attr:`MouseButton.UNKNOWN`, moves the cursor and sets :attr:`highlight`.

        A press and a release on the same character select nothing.
        A release over another widget is not seen.
        The drag is then dropped, with nothing selected, by the next key, a new text, the next press,
        or a render without focus.

        >>> from urwid import Edit
        >>> size = (20,)
        >>> e = Edit("", "words here")
        >>> e.mouse_event(size, "mouse press", 1, 2, 0, True)
        True
        >>> e.edit_pos
        2
        >>> e = Edit("", "words here", mouse_select=True)
        >>> e.mouse_event(size, "mouse press", 1, 1, 0, True)
        True
        >>> e.mouse_event(size, "mouse release", 1, 3, 0, True)
        True
        >>> e.selected_text
        'ord'

        :returns: whether the event was handled, as the flow above shows.
        """
        self._kill_last = None  # a click may have moved the focus away and back
        release = event.endswith("mouse release")
        if event.endswith("mouse press"):
            if button != MouseButton.LEFT:
                return False
            if self._select_anchor is not None:  # an earlier press released over another widget
                self._select_anchor = None
                self._invalidate()
            if not self.move_cursor_to_coords(size, col, row):
                return False
            self._select_anchor = self._edit_pos
            return True
        if self._select_anchor is None or not (
            (event.endswith("mouse drag") and button == MouseButton.LEFT)
            or (release and button in {MouseButton.LEFT, MouseButton.UNKNOWN})
        ):
            return False  # the press was over another widget, or the event belongs to another button
        if not self.mouse_select:
            if release:
                self._select_anchor = None
            return button == MouseButton.LEFT and self.move_cursor_to_coords(size, col, row)
        (maxcol,) = size
        top_y = self.position_coords(maxcol, 0)[1]
        self.move_cursor_to_coords(size, col, min(max(row, top_y), len(self.get_line_translation(maxcol)) - 1))
        if release:
            selected, self._select_anchor = self._drag_range(), None
            self.highlight = selected
        return True

    def _drag_range(self) -> tuple[int, int] | None:
        """Return the range the unfinished :attr:`mouse_select` drag selects, or ``None`` when it selects nothing.

        It runs from the smaller of the press offset and the cursor to after the character at the larger one.
        A newline at the larger one and the end of the text are not taken in.
        """
        anchor, pos, text = self._select_anchor, self._edit_pos, self._edit_text
        if anchor is None or anchor == pos:
            return None
        start, last = sorted((anchor, pos))
        if last == len(text) or text[last : last + 1] in {"\n", b"\n"}:
            return start, last
        return start, move_next_char(text, last, len(text))

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> TextCanvas | CompositeCanvas:
        """Render edit widget and return canvas.

        Include cursor when in focus.

        >>> from urwid import Edit
        >>> edit = Edit("? ", "yes")
        >>> c = edit.render((10,), focus=True)
        >>> c.text
        [b'? yes     ']
        >>> c.cursor
        (5, 0)
        """
        self._shift_view_to_cursor = focus
        if not focus and self._select_anchor is not None:
            # stands in for a release over another widget, which this widget never sees;
            # the invalidation drops the focused canvas that shows the unfinished range
            self._select_anchor = None
            self._invalidate()

        (maxcol,) = size
        if (placeholder := self._placeholder_layout(maxcol)) is not None:
            text, attr, trans = placeholder
        else:
            text, attr = self.get_text()
            trans = self.get_line_translation(maxcol, (text, attr))
            selected = self._drag_range() if self.mouse_select and self._select_anchor is not None else self._highlight
            if self._select_attr is not None and selected is not None:
                attr = self._layer_selection(attr, len(text), *(len(self.caption) + offset for offset in selected))
        canv: TextCanvas | CompositeCanvas = apply_text_layout(text, attr, trans, maxcol)

        if focus:
            canv = CompositeCanvas(canv)
            canv.cursor = self.get_cursor_coords(size)

        if (severity := self.severity) is not None:
            if focus and severity in self._validation_focus_attr:
                attr_map = self._validation_focus_attr[severity]
            elif severity in self._validation_attr:
                attr_map = self._validation_attr[severity]
            else:
                attr_map = None
            if attr_map is not None:
                canv = CompositeCanvas(canv)
                canv.fill_attr_apply(attr_map)
        return canv

    def _layer_selection(
        self,
        attr: list[tuple[Hashable, int]],
        length: int,
        start: int,
        stop: int,
    ) -> list[tuple[Hashable, int]]:
        """Return *attr* with :attr:`select_attr` placed over the runs from *start* to *stop*.

        :param attr: run-length encoded attributes of the displayed text, which may stop before its end
        :param length: length of the displayed text
        :param start: first offset of the range in the displayed text
        :param stop: offset after the range in the displayed text
        """
        runs: list[tuple[Hashable, int]] = []
        pos = 0
        for run_attr, run in (*attr, (None, max(length - rle_len(attr), 0))):
            end = pos + run
            for piece_start, piece_end, piece_attr in (
                (pos, min(end, start), run_attr),
                (max(pos, start), min(end, stop), LayeredAttr.layer(self._select_attr, run_attr)),
                (max(pos, stop), end, run_attr),
            ):
                if piece_end > piece_start:
                    runs.append((piece_attr, piece_end - piece_start))
            pos = end
        return runs

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        r"""Return the number of rows the rendered edit requires, including a :attr:`placeholder` that grows it.

        >>> from urwid import Edit
        >>> Edit("", multiline=True, placeholder="line 1\nline 2").rows((20,))
        2
        """
        if (placeholder := self._placeholder_layout(size[0])) is not None:
            return len(placeholder[2])
        return self._w.rows(size, focus)

    def _placeholder_layout(
        self,
        maxcol: int,
    ) -> (
        tuple[
            str | bytes,
            list[tuple[Hashable, int]],
            list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]],
        ]
        | None
    ):
        """Return the text, attributes and layout of the caption followed by the :attr:`placeholder`.

        The layout has the rows :meth:`rows` reports.
        It is laid out through the layout object, because the wrapped :class:`Text` caches the caption-only layout.

        :returns: ``None`` when no placeholder is drawn: none is set, :attr:`edit_text` is not empty,
            or the caption-only layout has to be shifted to show the cursor, which the placeholder layout would not be.
        """
        if self._placeholder_ta is None or self._edit_text:
            return None
        caption_trans = self._w.get_line_translation(maxcol)
        shift_view_to_cursor, self._shift_view_to_cursor = self._shift_view_to_cursor, True
        try:
            # decided as if focused, so that rows() and an unfocused render() agree with a focused render()
            shifted = self.get_line_translation(maxcol) != caption_trans
        finally:
            self._shift_view_to_cursor = shift_view_to_cursor
        if shifted:
            return None

        placeholder_text, placeholder_attrib = self._placeholder_ta
        text = self._caption + placeholder_text  # type: ignore[operator]  # type normalised
        attrib = [*self._padded_caption_attrib(), *placeholder_attrib]

        trans = self._w.layout.layout(text, maxcol, self._w.align, self._w.wrap)
        grow = self.multiline if self._placeholder_grow is None else self._placeholder_grow
        rows = max(len(caption_trans), len(trans)) if grow else len(caption_trans)
        return text, attrib, [*trans[:rows], *([] for _row in range(rows - len(trans)))]

    def get_line_translation(
        self,
        maxcol: int,
        ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None = None,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
        """Return the line translation for `ta`, shifted to keep the cursor visible if needed."""
        trans = self._w.get_line_translation(maxcol, ta)
        if not self._shift_view_to_cursor:
            return trans

        if self._w.wrap in (WrapMode.SPACE, WrapMode.ANY):
            # Wrapping modes grow the number of rows instead of clipping a row's width,
            # so there is never a partially hidden row to scroll horizontally into view.
            return trans

        text = self._displayed_text()
        if self._w.wrap == WrapMode.ELLIPSIS and self._w.layout.supports_wrap_mode(WrapMode.CLIP):
            # The ellipsis replaces the text past the cut, so no shift could bring a cursor there into view:
            # the row with the cursor is clipped instead, and the other rows keep their ellipsis.
            clipped = self._w.layout.layout(text, maxcol, self._w.align, WrapMode.CLIP)
            if len(clipped) == len(trans):  # a different row count would disagree with rows()
                cursor_row = text_layout.calc_coords(text, clipped, self.edit_pos + len(self.caption))[1]
                trans = [*trans[:cursor_row], clipped[cursor_row], *trans[cursor_row + 1 :]]
        x, y = text_layout.calc_coords(text, trans, self.edit_pos + len(self.caption))
        if x < 0:
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -x)],
                *trans[y + 1 :],
            ]

        pos = self.edit_pos + len(self.caption)
        # the cursor after the last character of a row, or on bytes that are not valid UTF-8, needs one column
        cursor_width = 1
        if pos < len(text) and text[pos : pos + 1] not in {"\n", b"\n"}:
            with contextlib.suppress(UnicodeDecodeError):
                cursor_width = max(calc_width(text, pos, move_next_char(text, pos, len(text))), 1)
        if x + cursor_width > maxcol:
            if cursor_width > maxcol:
                # the character under the cursor cannot be shown whole: start the row with it
                shift = x
            else:
                try:
                    shift = self._boundary_column(text, trans[y], x + cursor_width - maxcol)
                except UnicodeDecodeError:
                    shift = x + cursor_width - maxcol  # a row that is not valid UTF-8 has no characters to keep whole
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -shift)],
                *trans[y + 1 :],
            ]

        return trans

    @staticmethod
    def _boundary_column(
        text: str | bytes,
        line: list[tuple[int, int, int | bytes] | tuple[int, int | None]],
        min_col: int,
    ) -> int:
        """Return the first screen column of *line*, from *min_col* on, that does not split a character.

        :param text: text that *line* is a layout row of
        :param line: one row of a layout structure
        :param min_col: the column to start looking from
        :returns: *min_col* or the column after it where the next character starts;
            the width of *line* when no character starts after *min_col*.
        """
        col = 0
        for seg in line:
            s = text_layout.LayoutSegment(seg)
            if s.offs is None or s.end is None:
                # a shift, inserted spaces or inserted text: no character spans its columns
                if col + s.sc >= min_col:
                    return max(col, min_col)
                col += s.sc
                continue
            pos = s.offs
            while col < min_col and pos < s.end:
                next_pos = move_next_char(text, pos, s.end)
                col += calc_width(text, pos, next_pos)
                pos = next_pos
            if col >= min_col:
                return col
        return col

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        """
        Return the (*x*, *y*) coordinates of cursor within widget, or ``None`` when it has no columns to show it in.

        >>> from urwid import Edit
        >>> Edit("? ", "yes").get_cursor_coords((10,))
        (5, 0)
        >>> Edit("? ", "yes").get_cursor_coords((0,)) is None
        True
        """
        (maxcol,) = size

        self._shift_view_to_cursor = True
        if maxcol == 0:
            return None
        x, y = self.position_coords(maxcol, self.edit_pos)
        if self._w.wrap in (WrapMode.SPACE, WrapMode.ANY) and x >= maxcol:
            # The cursor sits right after a row that is already full and entirely visible.
            # Clamp onto its last column instead of scrolling that row out of view for a wrap
            # that has not happened yet.
            x = maxcol - 1
        return x, y

    def _cursor_row(self, size: tuple[int]) -> int | None:
        if (coords := self.get_cursor_coords(size)) is not None:
            return coords[1]
        if size[0] == 0:
            # No columns means no cursor, but the edit position still has a row.
            return self.position_coords(0, self.edit_pos)[1]
        # An override reports no cursor to move from.
        return None

    def position_coords(self, maxcol: int, pos: int) -> tuple[int, int]:
        """Return (*x*, *y*) coordinates for an offset into self.edit_text."""
        p = pos + len(self.caption)
        trans = self.get_line_translation(maxcol)
        x, y = text_layout.calc_coords(self._displayed_text(), trans, p)
        return x, y
