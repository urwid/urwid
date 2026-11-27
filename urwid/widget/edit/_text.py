"""Text and cursor layer of :class:`Edit`."""

from __future__ import annotations

import typing
import unicodedata

from urwid.str_util import _grapheme_boundary, is_wide_char, move_next_char
from urwid.util import decompose_tagmarkup

from ._completion import _EditCompletionState

if typing.TYPE_CHECKING:
    from collections import deque
    from collections.abc import Hashable
    from typing import Literal

    from urwid import text_layout
    from urwid.util import _TagMarkup

    from ..constants import Align, WrapMode


class _EditText(_EditCompletionState):
    """Caption, edit text, cursor position, mask, placeholder and text layout of :class:`Edit`."""

    _applied_edit_pos: int | None
    _attrib: list[tuple[Hashable, int]]
    _caption: str | bytes
    _completion_hold: bool
    _edit_depth: int = 0  # pylint reads the augmented assignments of _EditUndo as no-member without a value
    _edit_pos: int
    _highlight: tuple[int, int] | None
    _kill_last: tuple[int, str | bytes] | None
    _max_length: int | None
    _pending_edit_pos: int | None
    _placeholder: _TagMarkup | None
    _placeholder_grow: bool | None
    _placeholder_ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None
    _redo_stack: deque[tuple[str | bytes, int]]
    _select_anchor: int | None
    _undo_before: tuple[str | bytes, int] | None
    _undo_run: tuple[str, str | bytes, int] | None
    _undo_stack: deque[tuple[str | bytes, int]]
    multiline: bool
    pref_col_maxcol: tuple[None, None] | tuple[int | Literal[Align.LEFT, Align.RIGHT], int]

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

    def _valid_insert(self, text: str | bytes, result_text: str | bytes) -> bool:
        """Return whether keys could have typed *text*, which leaves *result_text*.

        Each character of *text* passes :meth:`valid_char`, or is a newline with :attr:`multiline`,
        or a tab with :attr:`allow_tab`.
        A multibyte character of a byte string passes.
        A subclass whose keys refuse some texts as a whole judges *result_text* as well.
        """
        pos = 0
        while pos < len(text):
            next_pos = pos + 1 if isinstance(text, str) else move_next_char(text, pos, len(text))
            char = text[pos:next_pos]
            if not (
                (len(char) > 1 and isinstance(char, bytes))
                or self.valid_char(char)  # type: ignore[arg-type]  # valid_char() takes bytes too
                or (char in {"\n", b"\n"} and self.multiline)
                or (char in {"\t", b"\t"} and self.allow_tab)
            ):
                return False
            pos = next_pos
        return True

    @property
    def placeholder(self) -> _TagMarkup | None:
        """Markup drawn after the caption while :attr:`edit_text` is empty, or ``None`` for none.

        It is drawn focused or not, and it is never masked.
        It is not part of the text: :meth:`get_text`, :attr:`edit_text`, :attr:`max_length` and :meth:`pack`
        ignore it.
        It is drawn after :attr:`caption` and its attributes, not after the caption part of :meth:`get_text`.
        The cursor stays where it is without a placeholder, so with ``align="left"`` it is on its first column.
        With ``align="center"`` or ``align="right"`` the placeholder moves the caption left, and the cursor is
        inside the placeholder or after it.
        The placeholder is not drawn when the caption alone does not leave the cursor a column to show in.

        :raises TagMarkupException: on assignment, the markup is not valid text markup.
        :raises UnicodeError: on assignment, the text cannot be converted to the type of the caption.
        """
        return self._placeholder

    @placeholder.setter
    def placeholder(self, placeholder: _TagMarkup | None) -> None:
        if placeholder is None:
            self._placeholder_ta = None
        else:
            text, attrib = decompose_tagmarkup(placeholder)
            self._placeholder_ta = self._normalize_to_caption(text), attrib
        self._placeholder = placeholder
        self._invalidate()

    @property
    def placeholder_grow(self) -> bool | None:
        """Whether a :attr:`placeholder` laid out on more rows than the empty edit adds rows.

        ``False`` cuts the placeholder to the rows of the empty edit, so the height does not change on the first key.
        ``True`` adds rows while the edit is empty.
        ``None`` grows a :attr:`multiline` edit and cuts a single-line one.
        """
        return self._placeholder_grow

    @placeholder_grow.setter
    def placeholder_grow(self, placeholder_grow: bool | None) -> None:
        self._placeholder_grow = placeholder_grow
        self._invalidate()

    def _sync_wrapped(self) -> None:
        """Synchronize the wrapped Text widget with current caption+edit_text state."""
        if type(self).get_text is _EditText.get_text:
            text, attrib = self._caption_and_text(), self._attrib
        else:
            text, attrib = self.get_text()
        self._w._text = text  # pylint: disable=protected-access
        self._w._attrib = attrib  # pylint: disable=protected-access
        self._w._invalidate()

    def get_text(self) -> tuple[str | bytes, list[tuple[Hashable, int]]]:
        """Return ``(text, display attributes)``.

        See :meth:`Text.get_text` for details.

        Text returned includes the caption and edit_text, possibly masked.
        The attributes are those of the caption, followed by :attr:`edit_attrib` or the runs of :attr:`highlighter`.
        The caption attributes are padded to the caption length only when edit runs follow them.
        The edit runs cover the string after the caption,
        so an override that changes the length of that string returns matching runs itself.
        Layout and cursor methods call an override of this method for the displayed string.

        >>> from urwid import Edit
        >>> Edit("What? ", "oh, nothing.").get_text()
        ('What? oh, nothing.', [])
        >>> Edit(("bright", "user@host:~$ "), "ls").get_text()
        ('user@host:~$ ls', [('bright', 13)])
        >>> Edit("password:", "seekrit", mask="*").get_text()
        ('password:*******', [])

        :raises ValueError: the text of the markup :attr:`highlighter` returned differs from :attr:`edit_text`.
        """
        text = self._caption_and_text()
        if not (runs := self._edit_runs()):
            return text, self._attrib
        return text, [*self._padded_caption_attrib(), *runs]

    def _displayed_text(self) -> str | bytes:
        """Return the caption and edit text as :meth:`get_text` shows them.

        An override of :meth:`get_text` is called, because it may show the text differently.
        The method of this class is not called, so that no attributes are built and the highlighter is not called.
        """
        if type(self).get_text is not _EditText.get_text:
            return self.get_text()[0]
        return self._caption_and_text()

    def _caption_and_text(self) -> str | bytes:
        """Return the caption followed by the edit text, masked when :attr:`mask` is set."""
        if self._mask is None:
            return self._caption + self._edit_text  # type: ignore[operator]  # type normalised
        return self._caption + (self._mask * len(self._edit_text))  # type: ignore[operator]

    def _padded_caption_attrib(self) -> list[tuple[Hashable, int]]:
        """Return the caption attributes, with a run of ``None`` up to the end of the caption."""
        caption_attrib = self._attrib.copy()
        if (uncovered := len(self._caption) - sum(run for _attr, run in caption_attrib)) > 0:
            caption_attrib.append((None, uncovered))
        return caption_attrib

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

    def set_caption(self, caption: _TagMarkup) -> None:
        """
        Set the caption markup for this widget.

        :param caption: markup for caption preceding edit_text, see
                        :meth:`Text.__init__` for description of text markup.

        >>> from urwid import Edit
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
        Sends ``"edit_pos"`` when the position differs from the previous one.

        A key, the mouse and :meth:`set_edit_text` move the cursor through this method,
        so a subclass that has to follow the cursor overrides it or connects to ``"edit_pos"``.
        The :attr:`edit_pos` property calls this base method directly, so it bypasses an override
        and still sends ``"edit_pos"``.

        :param pos: cursor position

        >>> from urwid import Edit
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
        old_pos, self._edit_pos = self._edit_pos, pos
        self._invalidate()
        if not self._completion_hold and (self._edit_text, pos) != self._completion_applied:
            self._end_completion()
        if pos != old_pos:
            self._emit("edit_pos", old_pos, pos)

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
        :raises TypeError: :attr:`validator` returned something else than the types it lists;
            the text is changed already.

        Called from elsewhere than a key, :meth:`editing`, :meth:`undo` or :meth:`redo`, it clears the undo history,
        see :attr:`undo_limit`.

        >>> from urwid import Edit
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
        if not self._edit_depth:
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._undo_before = self._undo_run = None
            self._kill_last = None
        self._select_anchor = None
        self.highlight = None
        self._emit("change", text)
        old_text = self._edit_text
        if text != old_text:
            self._highlight_text_changed()
        hold, self._completion_hold = self._completion_hold, True
        try:
            self._edit_text = text
            self._sync_wrapped()
            if edit_pos is None:
                edit_pos = min(self._edit_pos, len(text)) if pending_edit_pos is None else pending_edit_pos
            self.set_edit_pos(edit_pos)

            self._emit("postchange", old_text)
            self._run_validator()
        finally:
            self._completion_hold = hold
        if pending_edit_pos is not None:
            self._applied_edit_pos = self.edit_pos
        if not hold and (self._edit_text, self._edit_pos) != self._completion_applied:
            self._end_completion()
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

        >>> from urwid import Edit
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

    @property
    def highlight(self) -> tuple[int, int] | None:
        """The selected range of :attr:`edit_text` as ``(start, stop)`` offsets with ``start < stop``, or ``None``.

        Typing, :meth:`insert_text` and the delete keys replace or delete the range.
        A cursor move and a new text clear it.
        Setting it does not move the cursor.
        :attr:`select_attr` draws it, and :attr:`mouse_select` lets a mouse drag set it.
        It is unrelated to :attr:`highlighter`, which colours the text by its content.

        On assignment the offsets are put in order and clipped to the text.
        An empty range is stored as ``None``.
        Otherwise *start* moves back and *stop* forward to grapheme cluster boundaries.
        A changed value redraws the widget and sends ``"highlight"`` with the old and the new value.

        >>> from urwid import Edit
        >>> e = Edit("", "hello world")
        >>> e.highlight = (11, 6)
        >>> e.highlight
        (6, 11)
        >>> e.highlight = (3, 3)
        >>> e.highlight is None
        True

        :raises ValueError: on assignment, the value is a sequence of other than two offsets.
        :raises TypeError: on assignment, the value is not ``None`` and not a sequence of integers.
        """
        return self._highlight

    @highlight.setter
    def highlight(self, highlight: tuple[int, int] | None) -> None:
        if highlight is not None:
            start, stop = sorted(min(max(offset, 0), len(self._edit_text)) for offset in highlight)
            if start == stop:  # dropped before widening, which would turn it into the cluster around it
                highlight = None
            else:
                highlight = (
                    _grapheme_boundary(self._edit_text, start, forward=False),
                    _grapheme_boundary(self._edit_text, stop, forward=True),
                )
        if highlight == self._highlight:
            return
        old, self._highlight = self._highlight, highlight
        self._invalidate()
        self._emit("highlight", old, highlight)

    @property
    def selected_text(self) -> str:
        """Return the text in the :attr:`highlight` range, or an empty text when nothing is selected.

        With :attr:`mask` set it is the real text, not the mask characters drawn for it.

        >>> from urwid import Edit
        >>> e = Edit("", "hello world")
        >>> e.highlight = (0, 5)
        >>> e.selected_text
        'hello'
        """
        if self._highlight is None:
            return self._edit_text[:0]
        start, stop = self._highlight
        return self._edit_text[start:stop]

    def insert_text(self, text: str) -> None:
        """Insert text at the cursor position and update cursor.

        This method is used by the keypress() method when inserting
        one or more characters into edit_text.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :raises ValueError: the result is longer than :attr:`max_length`; the text is left as it was.

        >>> from urwid import Edit
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
