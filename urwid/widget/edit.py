from __future__ import annotations

import string
import typing

from urwid import text_layout
from urwid.canvas import CompositeCanvas, apply_text_layout
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.str_util import is_wide_char, move_next_char, move_prev_char
from urwid.util import decompose_tagmarkup

from .constants import Align, Sizing, WrapMode
from .text import Text, TextError
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from typing_extensions import Literal

    from urwid.canvas import TextCanvas

    _TagMarkup = typing.Union[str, tuple[Hashable, typing.Union[str]], list["_TagMarkup"]]


class EditError(TextError):
    pass


class Edit(WidgetWrap[Text]):
    """
    Text editing widget implements cursor movement, text insertion and
    deletion.  A caption may prefix the editing area.  Uses text class
    for text layout.

    Users of this class may listen for ``"change"`` or ``"postchange"``
    events.  See :func:``connect_signal``.

    * ``"change"`` is sent just before the value of edit_text changes.
      It receives the new text as an argument.  Note that ``"change"`` cannot
      change the text in question as edit_text changes the text afterwards.
    * ``"postchange"`` is sent after the value of edit_text changes.
      It receives the old value of the text as an argument and thus is
      appropriate for changing the text.  It is possible for a ``"postchange"``
      event handler to get into a loop of changing the text and then being
      called when the event is re-emitted.  It is up to the event
      handler to guard against this case (for instance, by not changing the
      text if it is signaled for text that it has already changed once).
    """

    _sizing = frozenset([Sizing.FLOW])
    _selectable = True
    ignore_focus = False
    # (this variable is picked up by the MetaSignals metaclass)
    signals: typing.ClassVar[list[str]] = ["change", "postchange"]

    def valid_char(self, ch: str) -> bool:
        """
        Filter for text that may be entered into this widget by the user

        :param ch: character to be inserted
        :type ch: str

        This implementation returns True for all printable characters.
        """
        return is_wide_char(ch, 0) or (len(ch) == 1 and ord(ch) >= 32)

    def __init__(
        self,
        caption: _TagMarkup = "",
        edit_text: str = "",
        multiline: bool = False,
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        allow_tab: bool = False,
        edit_pos: int | None = None,
        layout: text_layout.TextLayout | None = None,
        mask: str | None = None,
    ) -> None:
        """
        :param caption: markup for caption preceding edit_text, see :class:`Text` for description of text markup.
        :type caption: text markup
        :param edit_text: initial text for editing, type (bytes or str) must match the text in the caption
        :type edit_text: bytes or str
        :param multiline: True: 'enter' inserts newline  False: return it
        :type multiline: bool
        :param align: typically 'left', 'center' or 'right'
        :type align: text alignment mode
        :param wrap: typically 'space', 'any' or 'clip'
        :type wrap: text wrapping mode
        :param allow_tab: True: 'tab' inserts 1-8 spaces  False: return it
        :type allow_tab: bool
        :param edit_pos: initial position for cursor, None:end of edit_text
        :type edit_pos: int
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance
        :param mask: hide text entered with this character, None:disable mask
        :type mask: bytes or str

        >>> Edit()
        <Edit selectable flow widget '' edit_pos=0>
        >>> Edit("Y/n? ", "yes")
        <Edit selectable flow widget 'yes' caption='Y/n? ' edit_pos=3>
        >>> Edit("Name ", "Smith", edit_pos=1)
        <Edit selectable flow widget 'Smith' caption='Name ' edit_pos=1>
        >>> Edit("", "3.14", align="right")
        <Edit selectable flow widget '3.14' align='right' edit_pos=4>
        """
        super().__init__(Text("", align, wrap, layout))
        self.multiline = multiline
        self.allow_tab = allow_tab
        self._edit_pos = 0
        self._caption, self._attrib = decompose_tagmarkup(caption)  # type: ignore[arg-type]
        self._edit_text = ""
        self.highlight: tuple[int, int] | None = None
        self._mask: str | None = None
        self._shift_view_to_cursor = False
        self.pref_col_maxcol: tuple[None, None] | tuple[int | Literal[Align.LEFT, Align.RIGHT], int] = (None, None)
        self.set_edit_text(edit_text)
        if edit_pos is None:
            edit_pos = len(edit_text)
        self.set_edit_pos(edit_pos)
        self.set_mask(mask)

    def selectable(self) -> bool:
        """Selectable mark.

        Wrapped Text widget is not selectable while the edit widget has to be selectable.
        """
        return True

    def sizing(self) -> frozenset[Sizing]:
        """Sizing information.

        Edit widget sizing is narrower than Text: we cannot predict the final input length.
        """
        return self._sizing

    def _repr_words(self) -> list[str]:
        return [
            *super()._repr_words(),
            repr(self._edit_text),
            *([f"caption={self._caption!r}"] if self._caption else []),
            *(["multiline"] if self.multiline is True else []),
        ]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "align": self._w.align,
            "wrap": self._w.wrap,
            "edit_pos": self._edit_pos,
        }
        return remove_defaults(attrs, Edit.__init__)

    def _sync_wrapped(self) -> None:
        """Synchronize the wrapped Text widget with current caption+edit_text state."""
        text, attrib = self.get_text()
        self._w._text = text  # pylint: disable=protected-access
        self._w._attrib = attrib  # pylint: disable=protected-access
        self._w._invalidate()

    def get_text(self) -> tuple[str | bytes, list[tuple[Hashable, int]]]:
        """
        Returns ``(text, display attributes)``. See :meth:`Text.get_text`
        for details.

        Text returned includes the caption and edit_text, possibly masked.

        >>> Edit("What? ", "oh, nothing.").get_text()
        ('What? oh, nothing.', [])
        >>> Edit(("bright", "user@host:~$ "), "ls").get_text()
        ('user@host:~$ ls', [('bright', 13)])
        >>> Edit("password:", "seekrit", mask="*").get_text()
        ('password:*******', [])
        """

        if self._mask is None:
            return self._caption + self._edit_text, self._attrib  # type: ignore[operator]  # type normalised

        return self._caption + (self._mask * len(self._edit_text)), self._attrib  # type: ignore[operator]

    @property
    def text(self) -> str | bytes:
        """
        Read-only property returning the complete bytes/unicode content
        of this widget (caption plus edit_text, possibly masked).
        """
        return self.get_text()[0]

    @property
    def attrib(self) -> list[tuple[Hashable, int]]:
        """
        Read-only property returning the run-length encoded display
        attributes of this widget.
        """
        return self.get_text()[1]

    def set_align_mode(self, mode: Literal["left", "center", "right"] | Align) -> None:
        """
        Set text alignment mode. See :meth:`Text.set_align_mode` for details.
        """
        self._w.set_align_mode(mode)
        self._invalidate()

    def set_wrap_mode(self, mode: Literal["space", "any", "clip", "ellipsis"] | WrapMode) -> None:
        """
        Set text wrapping mode. See :meth:`Text.set_wrap_mode` for details.
        """
        self._w.set_wrap_mode(mode)
        self._invalidate()

    def set_layout(
        self,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode,
        layout: text_layout.TextLayout | None = None,
    ) -> None:
        """
        Set the text layout object, alignment and wrapping modes at the same time.
        See :meth:`Text.set_layout` for details.
        """
        self._w.set_layout(align, wrap, layout)
        self._invalidate()

    align = property(lambda self: self._w.align, set_align_mode)
    wrap = property(lambda self: self._w.wrap, set_wrap_mode)

    @property
    def layout(self) -> text_layout.TextLayout:
        return self._w.layout

    def get_pref_col(self, size: tuple[int]) -> int:
        """
        Return the preferred column for the cursor, or the
        current cursor x value.  May also return ``'left'`` or ``'right'``
        to indicate the leftmost or rightmost column available.

        This method is used internally and by other widgets when
        moving the cursor up or down between widgets so that the
        column selected is one that the user would expect.

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
        >>> e = Edit("", "2\\nwords")
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
            return self.get_cursor_coords((maxcol,))[0]

        return typing.cast("int", pref_col)

    def set_caption(self, caption: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]) -> None:
        """
        Set the caption markup for this widget.

        :param caption: markup for caption preceding edit_text, see
                        :meth:`Text.__init__` for description of text markup.

        >>> e = Edit("")
        >>> e.set_caption("cap1")
        >>> print(e.caption)
        cap1
        >>> e.set_caption(("bold", "cap2"))
        >>> print(e.caption)
        cap2
        >>> e.attrib
        [('bold', 4)]
        >>> e.caption = "cap3"  # not supported because caption stores text but set_caption() takes markup
        Traceback (most recent call last):
        AttributeError: can't set attribute
        """
        self._caption, self._attrib = decompose_tagmarkup(caption)  # type: ignore[arg-type]
        self._sync_wrapped()
        self._invalidate()

    @property
    def caption(self) -> str | bytes:
        """
        Read-only property returning the caption for this widget.
        """
        return self._caption

    def set_edit_pos(self, pos: int) -> None:
        """
        Set the cursor position with a self.edit_text offset.
        Clips pos to [0, len(edit_text)].

        :param pos: cursor position
        :type pos: int

        >>> e = Edit("", "word")
        >>> e.edit_pos
        4
        >>> e.set_edit_pos(2)
        >>> e.edit_pos
        2
        >>> e.edit_pos = -1  # Urwid 0.9.9 or later
        >>> e.edit_pos
        0
        >>> e.edit_pos = 20
        >>> e.edit_pos
        4
        """
        pos = min(max(pos, 0), len(self._edit_text))
        self.highlight = None
        self.pref_col_maxcol = None, None
        self._edit_pos = pos
        self._invalidate()

    edit_pos = property(
        lambda self: self._edit_pos,
        set_edit_pos,
        doc="""
        Property controlling the edit position for this widget.
        """,
    )

    def set_mask(self, mask: str | None) -> None:
        """
        Set the character for masking text away.

        :param mask: hide text entered with this character, None:disable mask
        :type mask: bytes or unicode
        """

        self._mask = mask
        self._sync_wrapped()
        self._invalidate()

    def set_edit_text(self, text: str) -> None:
        """
        Set the edit text for this widget.

        :param text: text for editing, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode

        >>> e = Edit()
        >>> e.set_edit_text("yes")
        >>> print(e.edit_text)
        yes
        >>> e
        <Edit selectable flow widget 'yes' edit_pos=0>
        >>> e.edit_text = "no"  # Urwid 0.9.9 or later
        >>> print(e.edit_text)
        no
        """
        text = self._normalize_to_caption(text)  # type: ignore[assignment]
        self.highlight = None
        self._emit("change", text)
        old_text = self._edit_text
        self._edit_text = text
        self._sync_wrapped()
        self.edit_pos = min(self.edit_pos, len(text))

        self._emit("postchange", old_text)
        self._invalidate()

    def get_edit_text(self) -> str:
        """
        Return the edit text for this widget.

        >>> e = Edit("What? ", "oh, nothing.")
        >>> print(e.get_edit_text())
        oh, nothing.
        >>> print(e.edit_text)
        oh, nothing.
        """
        return self._edit_text

    edit_text = property(
        get_edit_text,
        set_edit_text,
        doc="""
        Property controlling the edit text for this widget.
        """,
    )

    def insert_text(self, text: str) -> None:
        """
        Insert text at the cursor position and update cursor.
        This method is used by the keypress() method when inserting
        one or more characters into edit_text.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode

        >>> e = Edit("", "42")
        >>> e.insert_text(".5")
        >>> e
        <Edit selectable flow widget '42.5' edit_pos=4>
        >>> e.set_edit_pos(2)
        >>> e.insert_text("a")
        >>> print(e.edit_text)
        42a.5
        """
        text = self._normalize_to_caption(text)  # type: ignore[assignment]
        result_text, result_pos = self.insert_text_result(text)
        self.set_edit_text(result_text)  # type: ignore[arg-type]  # normalisation happen
        self.set_edit_pos(result_pos)
        self.highlight = None

    def _normalize_to_caption(self, text: str | bytes) -> str | bytes:
        """Return text converted to the same type as self.caption (bytes or unicode)"""
        tu = isinstance(text, str)
        cu = isinstance(self._caption, str)
        if tu == cu:
            return text
        if tu:
            return text.encode("ascii")  # type: ignore[union-attr]  # follow python2's implicit conversion
        return text.decode("ascii")  # type: ignore[union-attr]

    def insert_text_result(self, text: str) -> tuple[str | bytes, int]:
        """
        Return result of insert_text(text) without actually performing the
        insertion.  Handy for pre-validation.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode
        """

        # if there's highlighted text, it'll get replaced by the new text
        text = self._normalize_to_caption(text)  # type: ignore[assignment]
        if self.highlight:
            start, stop = self.highlight
            btext, etext = self.edit_text[:start], self.edit_text[stop:]
            result_text = btext + etext
            result_pos = start
        else:
            result_text = self.edit_text
            result_pos = self.edit_pos

        try:
            result_text = result_text[:result_pos] + text + result_text[result_pos:]
        except (IndexError, TypeError) as exc:
            raise ValueError(repr((self.edit_text, result_text, text))).with_traceback(exc.__traceback__) from exc

        result_pos += len(text)
        return (result_text, result_pos)

    def keypress(
        self,
        size: tuple[int],
        key: str,
    ) -> str | None:
        """
        Handle editing keystrokes, return others.

        >>> e, size = Edit(), (20,)
        >>> e.keypress(size, "x")
        >>> e.keypress(size, "left")
        >>> e.keypress(size, "1")
        >>> print(e.edit_text)
        1x
        >>> e.keypress(size, "backspace")
        >>> e.keypress(size, "end")
        >>> e.keypress(size, "2")
        >>> print(e.edit_text)
        x2
        >>> e.keypress(size, "shift f1")
        'shift f1'
        """
        pos = self.edit_pos
        if self.valid_char(key):
            if isinstance(key, str) and not isinstance(self._caption, str):
                key = key.encode("utf-8")  # type: ignore[assignment]
            self.insert_text(key)
            return None

        if key == "tab" and self.allow_tab:
            key = " " * (8 - (self.edit_pos % 8))
            self.insert_text(key)
            return None

        if key == "enter" and self.multiline:
            key = "\n"
            self.insert_text(key)
            return None

        if self._command_map[key] == Command.LEFT:
            if pos == 0:
                return key
            pos = move_prev_char(self.edit_text, 0, pos)
            self.set_edit_pos(pos)
            return None

        if self._command_map[key] == Command.RIGHT:
            if pos >= len(self.edit_text):
                return key
            pos = move_next_char(self.edit_text, pos, len(self.edit_text))
            self.set_edit_pos(pos)
            return None

        if self._command_map[key] in {Command.UP, Command.DOWN}:
            self.highlight = None

            _x, y = self.get_cursor_coords(size)
            pref_col = self.get_pref_col(size)
            if pref_col is None:
                raise ValueError(pref_col)

            if self._command_map[key] == Command.UP:
                y -= 1
            else:
                y += 1

            if not self.move_cursor_to_coords(size, pref_col, y):
                return key
            return None

        if key == "backspace":
            self.pref_col_maxcol = None, None
            if not self._delete_highlighted():
                if pos == 0:
                    return key
                pos = move_prev_char(self.edit_text, 0, pos)
                self.set_edit_text(self.edit_text[:pos] + self.edit_text[self.edit_pos :])
                self.set_edit_pos(pos)
                return None
            return None

        if key == "delete":
            self.pref_col_maxcol = None, None
            if not self._delete_highlighted():
                if pos >= len(self.edit_text):
                    return key
                pos = move_next_char(self.edit_text, pos, len(self.edit_text))
                self.set_edit_text(self.edit_text[: self.edit_pos] + self.edit_text[pos:])
                return None
            return None

        if self._command_map[key] in {Command.MAX_LEFT, Command.MAX_RIGHT}:
            self.highlight = None
            self.pref_col_maxcol = None, None

            _x, y = self.get_cursor_coords(size)

            if self._command_map[key] == Command.MAX_LEFT:
                self.move_cursor_to_coords(size, Align.LEFT, y)
            else:
                self.move_cursor_to_coords(size, Align.RIGHT, y)
            return None

        # key wasn't handled
        return key

    def move_cursor_to_coords(
        self,
        size: tuple[int],
        x: int | Literal[Align.LEFT, Align.RIGHT],
        y: int,
    ) -> bool:
        """
        Set the cursor position with (x,y) coordinates.
        Returns True if move succeeded, False otherwise.

        >>> size = (10,)
        >>> e = Edit("", "edit\\ntext")
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

        pos = text_layout.calc_pos(self.get_text()[0], trans, x, y)
        e_pos = min(max(pos - len(self.caption), 0), len(self.edit_text))
        self.edit_pos = e_pos
        self.pref_col_maxcol = x, maxcol
        self._invalidate()
        return True

    def mouse_event(
        self,
        size: tuple[int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """
        Move the cursor to the location clicked for button 1.

        >>> size = (20,)
        >>> e = Edit("", "words here")
        >>> e.mouse_event(size, "mouse press", 1, 2, 0, True)
        True
        >>> e.edit_pos
        2
        """
        if button == 1:
            return self.move_cursor_to_coords(size, col, row)
        return False

    def _delete_highlighted(self) -> bool:
        """
        Delete all highlighted text and update cursor position, if any
        text is highlighted.
        """
        if not self.highlight:
            return False
        start, stop = self.highlight
        btext, etext = self.edit_text[:start], self.edit_text[stop:]
        self.set_edit_text(btext + etext)
        self.edit_pos = start
        self.highlight = None
        return True

    def render(
        self,
        size: tuple[int],
        focus: bool = False,
    ) -> TextCanvas | CompositeCanvas:
        """
        Render edit widget and return canvas.  Include cursor when in
        focus.

        >>> edit = Edit("? ", "yes")
        >>> c = edit.render((10,), focus=True)
        >>> c.text
        [b'? yes     ']
        >>> c.cursor
        (5, 0)
        """
        self._shift_view_to_cursor = bool(focus)

        (maxcol,) = size
        text, attr = self.get_text()
        trans = self.get_line_translation(maxcol, (text, attr))
        canv: TextCanvas | CompositeCanvas = apply_text_layout(text, attr, trans, maxcol)

        if focus:
            canv = CompositeCanvas(canv)
            canv.cursor = self.get_cursor_coords(size)

        # .. will need to FIXME if I want highlight to work again
        # if self.highlight:
        #    hstart, hstop = self.highlight_coords()
        #    d.coords['highlight'] = [ hstart, hstop ]
        return canv

    def get_line_translation(
        self,
        maxcol: int,
        ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None = None,
    ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
        trans = self._w.get_line_translation(maxcol, ta)
        if not self._shift_view_to_cursor:
            return trans

        text, _ignore = self.get_text()
        x, y = text_layout.calc_coords(text, trans, self.edit_pos + len(self.caption))
        if x < 0:
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -x)],
                *trans[y + 1 :],
            ]

        if x >= maxcol:
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -(x - maxcol + 1))],
                *trans[y + 1 :],
            ]

        return trans

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int]:
        """
        Return the (*x*, *y*) coordinates of cursor within widget.

        >>> Edit("? ", "yes").get_cursor_coords((10,))
        (5, 0)
        """
        (maxcol,) = size

        self._shift_view_to_cursor = True
        return self.position_coords(maxcol, self.edit_pos)

    def position_coords(self, maxcol: int, pos: int) -> tuple[int, int]:
        """
        Return (*x*, *y*) coordinates for an offset into self.edit_text.
        """

        p = pos + len(self.caption)
        trans = self.get_line_translation(maxcol)
        x, y = text_layout.calc_coords(self.get_text()[0], trans, p)
        return x, y


class IntEdit(Edit):
    """Edit widget for integer values"""

    def valid_char(self, ch: str) -> bool:
        """
        Return true for decimal digits.
        """
        return len(ch) == 1 and ch in string.digits

    def __init__(self, caption: _TagMarkup = "", default: int | str | None = None) -> None:
        """
        caption -- caption markup
        default -- default edit value

        >>> IntEdit("", 42)
        <IntEdit selectable flow widget '42' edit_pos=2>
        """
        if default is not None:
            val = str(default)
        else:
            val = ""
        super().__init__(caption, val)

    def keypress(
        self,
        size: tuple[int],
        key: str,
    ) -> str | None:
        """
        Handle editing keystrokes.  Remove leading zeros.

        >>> e, size = IntEdit("", 5002), (10,)
        >>> e.keypress(size, "home")
        >>> e.keypress(size, "delete")
        >>> print(e.edit_text)
        002
        >>> e.keypress(size, "end")
        >>> print(e.edit_text)
        2
        """
        if unhandled := super().keypress(size, key):
            return unhandled

        # trim leading zeros
        while self.edit_pos > 0 and self.edit_text[:1] == "0":
            self.set_edit_pos(self.edit_pos - 1)
            self.set_edit_text(self.edit_text[1:])

        return None

    def value(self) -> int:
        """
        Return the numeric value of self.edit_text.

        >>> e, size = IntEdit(), (10,)
        >>> e.keypress(size, "5")
        >>> e.keypress(size, "1")
        >>> e.value() == 51
        True
        """
        if self.edit_text:
            return int(self.edit_text)

        return 0
