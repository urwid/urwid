"""Edit: a text editing widget, and IntEdit for integers."""

from __future__ import annotations

import contextlib
import string
import sys
import typing
import unicodedata

from urwid import text_layout
from urwid.canvas import CompositeCanvas, apply_text_layout
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.str_util import _grapheme_boundary, calc_width, is_wide_char, move_next_char, move_prev_char
from urwid.util import decompose_tagmarkup

from .constants import Align, Sizing, WrapMode
from .text import Text, TextError
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import Literal

    from urwid.canvas import TextCanvas
    from urwid.util import _TagMarkup


class EditError(TextError):
    """Edit related errors."""


class Edit(WidgetWrap[Text]):
    """Text editing widget implements cursor movement, text insertion and deletion.

    A caption may prefix the editing area.  Uses text class for text layout.

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
    * ``"submit"`` is sent when :kbd:`enter`, mapped to ``'activate'``, reaches an Edit with ``multiline=False``.
      It receives the edit text as an argument. :meth:`keypress` still returns the key.
    """

    _sizing = frozenset([Sizing.FLOW])
    _selectable = True
    ignore_focus = False
    # (this variable is picked up by the MetaSignals metaclass)
    signals: typing.ClassVar[list[str]] = ["change", "postchange", "submit"]

    def valid_char(self, ch: str) -> bool:
        """
        Filter for text that may be entered into this widget by the user.

        :param ch: character to be inserted

        This implementation returns True for a wide character and for any single character that is not a control
        character (Unicode category ``Cc``): the displays print a control character as ``?`` while the width
        calculation counts it as zero columns. A single byte is accepted unless it is a C0 control or DEL, because
        0x80-0xff are printable characters in a single-byte encoding.
        """
        if is_wide_char(ch, 0):
            return True
        if len(ch) != 1:
            return False
        if isinstance(ch, str):
            return unicodedata.category(ch) != "Cc"
        return 32 <= ord(ch) != 0x7F

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
        *,
        expand_tabs: bool = True,
        max_length: int | None = None,
    ) -> None:
        """Create the Edit widget.

        :param caption: markup for caption preceding edit_text, see :class:`Text` for description of text markup.
        :param edit_text: initial text for editing, type (bytes or str) must match the text in the caption
        :param multiline: ``True``: :kbd:`enter` inserts a newline, ``False``: return it
        :param align: typically 'left', 'center' or 'right'
        :param wrap: typically 'space', 'any' or 'clip'
        :param allow_tab: ``True``: :kbd:`tab` is inserted, ``False``: return it
        :param edit_pos: initial position for cursor, None:end of edit_text
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :param mask: hide text entered with this character, None:disable mask
        :param expand_tabs: ``True``: an inserted tab is spaces up to the next tab stop of the line,
            ``False``: a tab character
        :param max_length: the longest :attr:`edit_text` allowed, see :attr:`max_length`
        :raises ValueError: *max_length* is negative, or *edit_text* is longer than it.

        >>> Edit()
        <Edit selectable flow widget '' edit_pos=0>
        >>> Edit("Y/n? ", "yes")
        <Edit selectable flow widget 'yes' caption='Y/n? ' edit_pos=3>
        >>> Edit("Name ", "Smith", edit_pos=1)
        <Edit selectable flow widget 'Smith' caption='Name ' edit_pos=1>
        >>> Edit("", "3.14", align="right")
        <Edit selectable flow widget '3.14' align='right' edit_pos=4>
        >>> pin = Edit("PIN: ", "123", max_length=4)
        >>> pin.keypress((20,), "4")
        >>> pin.keypress((20,), "5")
        '5'
        >>> print(pin.edit_text)
        1234
        """
        super().__init__(Text("", align, wrap, layout))
        self.multiline = multiline
        self.allow_tab = allow_tab
        self.expand_tabs = expand_tabs
        self._edit_pos = 0
        self._caption, self._attrib = decompose_tagmarkup(caption)
        self._edit_text = ""
        self._max_length: int | None = None
        self.max_length = max_length
        self.highlight: tuple[int, int] | None = None
        self._mask: str | None = None
        self._shift_view_to_cursor = False
        self.pref_col_maxcol: tuple[None, None] | tuple[int | Literal[Align.LEFT, Align.RIGHT], int] = (None, None)
        # cursor position the next set_edit_text() call applies before "postchange", see _set_edit_text_and_pos()
        self._pending_edit_pos: int | None = None
        # cursor position set_edit_text() left after "postchange" when a pending one was given
        self._applied_edit_pos: int | None = None
        self.set_edit_text(edit_text)
        if edit_pos is None:
            edit_pos = len(edit_text)
        self.set_edit_pos(edit_pos)
        self.set_mask(mask)

    @property
    def max_length(self) -> int | None:
        """The longest :attr:`edit_text` allowed, or ``None`` for no limit.

        It is counted like :attr:`edit_pos`: in code points, or in bytes when the caption is bytes.
        A key that would go over it is refused, see :meth:`keypress`; :meth:`set_edit_text` and :meth:`insert_text`
        raise :exc:`ValueError` instead. Setting it negative or below the length of :attr:`edit_text` raises
        :exc:`ValueError` too.
        """
        return self._max_length

    @max_length.setter
    def max_length(self, max_length: int | None) -> None:
        if max_length is not None and max_length < 0:
            raise ValueError(f"max_length must not be negative, got {max_length}")
        if max_length is not None and len(self._edit_text) > max_length:
            raise ValueError(f"max_length {max_length} is shorter than the text of length {len(self._edit_text)}")
        self._max_length = max_length

    def selectable(self) -> bool:
        """Return True: this widget is always selectable.

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
            repr(self._edit_text if self._mask is None else self._mask * len(self._edit_text)),
            *([f"caption={self._caption!r}"] if self._caption else []),
            *(["multiline"] if self.multiline else []),
        ]

    def _repr_attrs(self) -> dict[str, typing.Any]:
        attrs = {
            **super()._repr_attrs(),
            "align": self._w.align,
            "wrap": self._w.wrap,
            "edit_pos": self._edit_pos,
            "mask": self._mask,
        }
        return remove_defaults(attrs, Edit.__init__)

    def _sync_wrapped(self) -> None:
        """Synchronize the wrapped Text widget with current caption+edit_text state."""
        text, attrib = self.get_text()
        self._w._text = text  # pylint: disable=protected-access
        self._w._attrib = attrib  # pylint: disable=protected-access
        self._w._invalidate()

    def get_text(self) -> tuple[str | bytes, list[tuple[Hashable, int]]]:
        """Return ``(text, display attributes)``.

        See :meth:`Text.get_text` for details.

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
        """Read-only property returning the complete bytes/unicode content of this widget.

        Includes caption plus edit_text, possibly masked.
        """
        return self.get_text()[0]

    @property
    def attrib(self) -> list[tuple[Hashable, int]]:
        """Read-only property returning the run-length encoded display attributes of this widget."""
        return self.get_text()[1]

    def set_align_mode(self, mode: Literal["left", "center", "right"] | Align) -> None:
        """Set text alignment mode. See :meth:`Text.set_align_mode` for details."""
        self._w.set_align_mode(mode)
        self._invalidate()

    def set_wrap_mode(self, mode: Literal["space", "any", "clip", "ellipsis"] | WrapMode) -> None:
        """Set text wrapping mode. See :meth:`Text.set_wrap_mode` for details."""
        self._w.set_wrap_mode(mode)
        self._invalidate()

    def set_layout(
        self,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode,
        layout: text_layout.TextLayout | None = None,
    ) -> None:
        """Set the text layout object, alignment and wrapping modes at the same time.

        See :meth:`Text.set_layout` for details.
        """
        self._w.set_layout(align, wrap, layout)
        self._invalidate()

    align = property(lambda self: self._w.align, set_align_mode)
    wrap = property(lambda self: self._w.wrap, set_wrap_mode)

    @property
    def layout(self) -> text_layout.TextLayout:
        """Return the :class:`TextLayout` instance used to lay out and wrap this widget's text."""
        return self._w.layout

    def get_pref_col(self, size: tuple[int]) -> int:
        r"""Return the preferred column for the cursor, or the current cursor x value.

        May also return ``'left'`` or ``'right'`` to indicate the leftmost or rightmost column available.

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

    def set_caption(self, caption: _TagMarkup) -> None:
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
        self._caption, self._attrib = decompose_tagmarkup(caption)
        self._sync_wrapped()
        self._invalidate()

    @property
    def caption(self) -> str | bytes:
        """Read-only property returning the caption for this widget."""
        return self._caption

    def set_edit_pos(self, pos: int) -> None:
        """Set the cursor position with a self.edit_text offset.

        Clips pos to [0, len(edit_text)], then moves a position inside a grapheme cluster back to
        the cluster start, so that the cursor never splits what is drawn as one character.

        :param pos: cursor position

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
        >>> e = Edit("", "e" + chr(0x301) + "x")  # "e" followed by a combining acute accent
        >>> e.set_edit_pos(1)
        >>> e.edit_pos
        0
        """
        pos = _grapheme_boundary(self._edit_text, min(max(pos, 0), len(self._edit_text)), forward=False)
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
        """
        self._mask = mask
        self._sync_wrapped()
        self._invalidate()

    def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
        """
        Set the edit text for this widget.

        :param text: text for editing, type (bytes or unicode)
                     must match the text in the caption
        :param edit_pos: cursor position to set before ``"postchange"`` is sent, clipped as by
            :meth:`set_edit_pos`; ``None`` keeps the current position, clipped to the new text.
            An override passes ``None`` on unchanged: an editing key gives its position to this method by another
            route, which an explicit position replaces.
        :raises ValueError: *text* is longer than :attr:`max_length`; the text is left as it was.

        >>> e = Edit()
        >>> e.set_edit_text("yes")
        >>> print(e.edit_text)
        yes
        >>> e
        <Edit selectable flow widget 'yes' edit_pos=0>
        >>> e.edit_text = "no"  # Urwid 0.9.9 or later
        >>> print(e.edit_text)
        no
        >>> e.set_edit_text("maybe", edit_pos=5)
        >>> e.edit_pos
        5
        """
        pending_edit_pos, self._pending_edit_pos = self._pending_edit_pos, None
        text = self._normalize_to_caption(text)  # type: ignore[assignment]
        if self._max_length is not None and len(text) > self._max_length:
            raise ValueError(f"text of length {len(text)} is longer than max_length {self._max_length}")
        self.highlight = None
        self._emit("change", text)
        old_text = self._edit_text
        self._edit_text = text
        self._sync_wrapped()
        self.edit_pos = min(self.edit_pos, len(text)) if edit_pos is None else edit_pos
        if edit_pos is None and pending_edit_pos is not None:
            # an editing key moves the cursor through set_edit_pos(), so that an override sees every move
            self.set_edit_pos(pending_edit_pos)

        self._emit("postchange", old_text)
        if pending_edit_pos is not None:
            self._applied_edit_pos = self.edit_pos
        self._invalidate()

    def _set_edit_text_and_pos(self, text: str | bytes, pos: int) -> None:
        """Replace the edit text and move the cursor to *pos*, so that "postchange" handlers already see *pos*.

        The position reaches :meth:`set_edit_text` through an attribute instead of its ``edit_pos`` argument,
        so that a subclass overriding it as ``set_edit_text(text)`` keeps working.
        The position is set again afterwards when the override never calls the base method, or moves the cursor
        after it returns, as editing keys did before "postchange" saw the new position.
        A cursor move made by a "postchange" handler is kept otherwise.
        """
        self._pending_edit_pos = pos
        self._applied_edit_pos = None
        try:
            self.set_edit_text(text)  # type: ignore[arg-type]  # normalisation happen
            applied = self._applied_edit_pos
        finally:
            self._pending_edit_pos = None
            self._applied_edit_pos = None
        if applied is None or self.edit_pos != applied:
            self.set_edit_pos(pos)

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
        """Insert text at the cursor position and update cursor.

        This method is used by the keypress() method when inserting
        one or more characters into edit_text.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :raises ValueError: the result is longer than :attr:`max_length`; the text is left as it was.

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
        self._set_edit_text_and_pos(result_text, result_pos)
        self.highlight = None

    def _normalize_to_caption(self, text: str | bytes) -> str | bytes:
        """Return text converted to the same type as self.caption (bytes or unicode)."""
        tu = isinstance(text, str)
        cu = isinstance(self._caption, str)
        if tu == cu:
            return text
        if tu:
            return text.encode("ascii")  # type: ignore[union-attr]  # follow python2's implicit conversion
        return text.decode("ascii")  # type: ignore[union-attr]

    def insert_text_result(self, text: str) -> tuple[str | bytes, int]:
        """Return result of insert_text(text) without actually performing the insertion.

        Handy for pre-validation.
        When the inserted text joins the grapheme cluster after it, the returned position is the end of that cluster.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :raises ValueError: *text* cannot be inserted at the current edit position. The message carries the texts
            involved unless a mask is set.
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
            detail = repr((self.edit_text, result_text, text)) if self._mask is None else "masked text"
            raise ValueError(detail).with_traceback(exc.__traceback__) from exc

        result_pos = _grapheme_boundary(result_text, result_pos + len(text), forward=True)
        return (result_text, result_pos)

    def _insert_typed_text(self, text: str | bytes) -> bool:
        """Insert the text a key produced, unless it would make :attr:`edit_text` longer than :attr:`max_length`.

        :returns: whether the text was inserted.
        """
        text = self._normalize_to_caption(text)
        result_text, _result_pos = self.insert_text_result(text)  # type: ignore[arg-type]  # normalised to the caption
        if self.max_length is not None and len(result_text) > self.max_length:
            return False
        self.insert_text(text)  # type: ignore[arg-type]  # normalised to the caption
        return True

    def keypress(
        self,
        size: tuple[int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """
        Handle editing keystrokes, return others.

        A key whose text would make :attr:`edit_text` longer than :attr:`max_length` inserts nothing and is
        returned, as :class:`IntEdit` returns a digit past its limit. A tab is inserted whole or not at all.

        The readline delete commands described in :class:`~urwid.CommandMap` go through :meth:`set_edit_text`.
        A subclass whose :meth:`set_edit_text` raises for some text has to handle those commands itself
        once an application binds them, or the exception leaves :meth:`keypress`.

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

        :raises ValueError: the preferred cursor column could not be determined.
        """
        pos = self.edit_pos
        if self.valid_char(key):
            typed = key.encode("utf-8") if isinstance(key, str) and not isinstance(self._caption, str) else key
            return None if self._insert_typed_text(typed) else key

        if key == "tab" and self.allow_tab:
            if not self.expand_tabs:
                return None if self._insert_typed_text("\t") else key
            layout = self._w.layout
            if not isinstance(layout, text_layout.StandardTextLayout):
                layout = text_layout.default_layout  # a custom layout has no tab stops
            text = self._edit_text
            tab, nl = ("\t", "\n") if isinstance(text, str) else (b"\t", b"\n")
            column = 0
            # pyrefly: ignore[bad-argument-type, no-matching-overload]  # isinstance() does not narrow nl and tab
            for idx, chunk in enumerate(text[text.rfind(nl, 0, pos) + 1 : pos].split(tab)):
                if idx:
                    column = layout.next_tab_stop(column)
                column += calc_width(chunk, 0, len(chunk))
            spaces = layout.next_tab_stop(column) - column
            if spaces and not self._insert_typed_text(" " * spaces):
                return key
            return None

        if key == "enter" and self.multiline:
            return None if self._insert_typed_text("\n") else key

        command = self._command_map[key]
        if key == "enter" and command == Command.ACTIVATE:
            self._emit("submit", self._edit_text)
            return key

        if command in {Command.WORD_LEFT, Command.WORD_RIGHT}:
            if (new_pos := self._word_boundary(pos, forward=command == Command.WORD_RIGHT)) == pos:
                return key
            self.set_edit_pos(new_pos)
            return None

        if command in {
            Command.DELETE_WORD_LEFT,
            Command.DELETE_WORD_RIGHT,
            Command.DELETE_TO_LINE_START,
            Command.DELETE_TO_LINE_END,
        }:
            text = self._edit_text
            nl = "\n" if isinstance(text, str) else b"\n"
            if command == Command.DELETE_WORD_LEFT:
                start, end = self._word_boundary(pos, forward=False), pos
            elif command == Command.DELETE_WORD_RIGHT:
                start, end = pos, self._word_boundary(pos, forward=True)
            elif command == Command.DELETE_TO_LINE_START:
                bol = text.rfind(nl, 0, pos)  # pyrefly: ignore[bad-argument-type]  # isinstance() does not narrow nl
                start, end = bol + 1, pos
            else:
                eol = text.find(nl, pos)  # pyrefly: ignore[bad-argument-type]  # isinstance() does not narrow nl
                start, end = pos, len(text) if eol < 0 else eol
            if start == end:
                return key
            self._set_edit_text_and_pos(text[:start] + text[end:], start)
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

            if (y := self._cursor_row(size)) is None:
                return key
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
                self._set_edit_text_and_pos(self.edit_text[:pos] + self.edit_text[self.edit_pos :], pos)
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

            if (y := self._cursor_row(size)) is None:
                return key

            if self._command_map[key] == Command.MAX_LEFT:
                self.move_cursor_to_coords(size, Align.LEFT, y)
            else:
                self.move_cursor_to_coords(size, Align.RIGHT, y)
            return None

        # key wasn't handled
        return key

    def _word_boundary(self, pos: int, *, forward: bool) -> int:
        """Return the edit position after the next word, or at the start of the previous word.

        A word is a run of characters whose first code point is a letter, a digit or an underscore.
        A multibyte character of a byte string counts as a letter.
        A masked text is one word, so that the cursor does not show where the hidden text has spaces.
        """
        text = self._edit_text
        end = len(text)
        if self._mask is not None:
            return end if forward else 0

        def in_word(char: str | bytes) -> bool:
            if isinstance(char, bytes):
                return char[:1].isalnum() or char[:1] == b"_" or len(char) > 1
            return char[:1].isalnum() or char[:1] == "_"

        for skip_word in (False, True):  # skip the separators before the word, then the word
            while pos != (end if forward else 0):
                other = move_next_char(text, pos, end) if forward else move_prev_char(text, 0, pos)
                if in_word(text[min(pos, other) : max(pos, other)]) != skip_word:
                    break
                pos = other
        return pos

    def move_cursor_to_coords(
        self,
        size: tuple[int],
        x: int | Literal[Align.LEFT, Align.RIGHT],
        y: int,
    ) -> bool:
        r"""Set the cursor position with (x,y) coordinates.

        :returns: True if move succeeded, False otherwise.

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

        pos = text_layout.calc_pos(self.get_text()[0], trans, x, y)
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
        """Delete all highlighted text and update cursor position, if any text is highlighted."""
        if not self.highlight:
            return False
        start, stop = self.highlight
        btext, etext = self.edit_text[:start], self.edit_text[stop:]
        self._set_edit_text_and_pos(btext + etext, start)
        self.highlight = None
        return True

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> TextCanvas | CompositeCanvas:
        """Render edit widget and return canvas.

        Include cursor when in focus.

        >>> edit = Edit("? ", "yes")
        >>> c = edit.render((10,), focus=True)
        >>> c.text
        [b'? yes     ']
        >>> c.cursor
        (5, 0)
        """
        self._shift_view_to_cursor = focus

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
        """Return the line translation for `ta`, shifted to keep the cursor visible if needed."""
        trans = self._w.get_line_translation(maxcol, ta)
        if not self._shift_view_to_cursor:
            return trans

        if self._w.wrap in (WrapMode.SPACE, WrapMode.ANY):
            # Wrapping modes grow the number of rows instead of clipping a row's width,
            # so there is never a partially hidden row to scroll horizontally into view.
            return trans

        text, _ignore = self.get_text()
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
        x, y = text_layout.calc_coords(self.get_text()[0], trans, p)
        return x, y


class IntEdit(Edit):
    """Edit widget for integer values."""

    def valid_char(self, ch: str) -> bool:
        """Return true for decimal digits."""
        return len(ch) == 1 and ch in string.digits

    def __init__(self, caption: _TagMarkup = "", default: int | str | None = None) -> None:
        """Create the IntEdit widget.

        :param caption: caption markup
        :param default: default edit value

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
        size: tuple[int],  # type: ignore[override]
        key: str,
    ) -> str | None:
        """
        Handle editing keystrokes.  Remove leading zeros.

        A digit is refused when the resulting text would exceed :func:`sys.get_int_max_str_digits` digits, so that
        :meth:`value` can convert whatever the user typed.

        >>> e, size = IntEdit("", 5002), (10,)
        >>> e.keypress(size, "home")
        >>> e.keypress(size, "delete")
        >>> print(e.edit_text)
        002
        >>> e.keypress(size, "end")
        >>> print(e.edit_text)
        2
        """
        max_digits = sys.get_int_max_str_digits()  # 0 means no limit
        if max_digits and self.valid_char(key) and len(self.insert_text_result(key)[0]) > max_digits:
            return key

        if unhandled := super().keypress(size, key):
            return unhandled

        text, pos = self._strip_leading_zeros(self.edit_text, self.edit_pos)
        if text != self.edit_text:
            self._set_edit_text_and_pos(text, pos)

        return None

    def insert_text(self, text: str) -> None:
        """Insert text at the cursor position and update the cursor, removing the leading zeros before the cursor.

        The result is set at once, so "change" and "postchange" are sent once, and not at all when the text stays
        the same.

        :param text: text for inserting, type (bytes or unicode) must match the text in the caption

        >>> e = IntEdit("", 0)
        >>> e.insert_text("7")
        >>> e
        <IntEdit selectable flow widget '7' edit_pos=1>
        """
        result_text, result_pos = self._strip_leading_zeros(*self.insert_text_result(text))
        if result_text == self.edit_text:
            self.set_edit_pos(result_pos)
        else:
            self._set_edit_text_and_pos(result_text, result_pos)

    @staticmethod
    def _strip_leading_zeros(text: str | bytes, pos: int) -> tuple[str | bytes, int]:
        """Return *text* without the leading zeros before *pos*, keeping a lone zero, and *pos* moved with it."""
        zero = b"0" if isinstance(text, bytes) else "0"
        zeros = 0
        while zeros < pos and text[zeros : zeros + 1] == zero and text[zeros + 1 : zeros + 2].isdigit():
            zeros += 1
        return text[zeros:], pos - zeros

    def value(self) -> int:
        """
        Return the numeric value of self.edit_text.

        >>> e, size = IntEdit(), (10,)
        >>> e.keypress(size, "5")
        >>> e.keypress(size, "1")
        >>> e.value() == 51
        True

        :raises ValueError: the text was set programmatically to something that is not a decimal integer,
            or to more digits than :func:`sys.get_int_max_str_digits` allows.
        """
        if self.edit_text:
            return int(self.edit_text)

        return 0
