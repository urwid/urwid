"""Edit: a text editing widget, and IntEdit for integers."""

from __future__ import annotations

import string
import sys
import typing
from collections import deque

from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.util import decompose_tagmarkup

from ..attr_map import _attr_map_dicts
from ..constants import Align, Severity, Sizing, ValidationMessage, WrapMode
from ..text import Text, TextError
from ._keys import _EditKeys

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Mapping, MutableSequence, Sequence
    from typing import Literal

    from urwid import text_layout
    from urwid.util import _TagMarkup

    from ..attr_map import _AttrMapLike


class EditError(TextError):
    """Edit related errors."""


class Edit(_EditKeys):
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
    * ``"cancel"`` is sent when a key mapped to ``'menu'``, :kbd:`esc` by default, reaches an Edit.
      It receives the edit text as an argument. :meth:`keypress` still returns the key.
    * ``"validation"`` is sent when :attr:`validation` changes.
      It receives the old and the new value as arguments.
    * ``"completion_cycle"`` is sent when a completion cycle starts, moves or ends, see :attr:`text_completer`.
      It receives the new value of :attr:`completion_cycle` as an argument.
    * ``"edit_pos"`` is sent when :attr:`edit_pos` changes, see :meth:`set_edit_pos`.
      It receives the old and the new position as arguments.
      A text change sends it before ``"postchange"`` when it moves the cursor,
      and does not send it when the cursor keeps its offset.
    """

    _sizing = frozenset([Sizing.FLOW])

    _selectable = True

    # (this variable is picked up by the MetaSignals metaclass)
    signals: typing.ClassVar[list[str]] = [
        "change",
        "postchange",
        "submit",
        "cancel",
        "validation",
        "completion_cycle",
        "edit_pos",
    ]

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
        placeholder: _TagMarkup | None = None,
        placeholder_grow: bool | None = None,
        validator: Callable[[str], ValidationMessage | str | Iterable[ValidationMessage] | None] | None = None,
        validation_attr: Mapping[Severity, _AttrMapLike] | None = None,
        validation_focus_attr: Mapping[Severity, _AttrMapLike] | None = None,
        highlighter: Callable[[str], _TagMarkup] | None = None,
        text_completer: Callable[[str, int], Sequence[tuple[str, int]]] | None = None,
        undo_limit: int = 0,
        kill_buffer: MutableSequence[str | bytes] | None = None,
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
        :param placeholder: markup drawn after the caption while :attr:`edit_text` is empty, see :attr:`placeholder`
        :param placeholder_grow: whether a placeholder taller than the empty edit adds rows,
            see :attr:`placeholder_grow`
        :param validator: called with :attr:`edit_text` to check it, see :attr:`validator`
        :param validation_attr: attribute map applied for each :class:`Severity`, see :attr:`validation_attr`
        :param validation_focus_attr: attribute map applied for each :class:`Severity` while focused,
            see :attr:`validation_focus_attr`
        :param highlighter: called with :attr:`edit_text` for its markup coloured by content, see :attr:`highlighter`
        :param text_completer: called with :attr:`edit_text` and :attr:`edit_pos` for completions,
            see :attr:`text_completer`
        :param undo_limit: the number of changes :meth:`undo` can take back, see :attr:`undo_limit`
        :param kill_buffer: list that the word and line delete commands put the deleted text into,
            see :attr:`kill_buffer`
        :raises ValueError: *max_length* is negative, or *edit_text* is longer than it.
            *undo_limit* is negative.
            *highlighter* is set together with *validation_attr* or *validation_focus_attr*.
        :raises TagMarkupException: *placeholder* is not valid text markup.
        :raises UnicodeError: the text of *placeholder* cannot be converted to the type of *caption*.
        :raises TypeError: *validator* returned something else than its documented return types for *edit_text*.
        :raises AttrMapError: a key or value of an attribute map of *validation_attr* or *validation_focus_attr*
            is not hashable.

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
        >>> Edit("Address: ", placeholder="10.0.0.1").render((20,)).text
        [b'Address: 10.0.0.1   ']
        """
        super().__init__(Text("", align, wrap, layout))
        self._placeholder_grow: bool | None = placeholder_grow
        self.multiline = multiline
        self.allow_tab = allow_tab
        self.expand_tabs = expand_tabs
        self._edit_pos = 0
        self._caption, self._attrib = decompose_tagmarkup(caption)
        self._placeholder: _TagMarkup | None = None
        # text and attributes of the placeholder markup, or None for no placeholder
        self._placeholder_ta: tuple[str | bytes, list[tuple[Hashable, int]]] | None = None
        self.placeholder = placeholder
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
        self._validator = validator
        self._validation: tuple[ValidationMessage, ...] = ()
        self._validation_attr = _attr_map_dicts(validation_attr)
        self._validation_focus_attr = _attr_map_dicts(validation_focus_attr)
        self._edit_attrib: list[tuple[Hashable, int]] = []
        # installed after the mask, so that it is never called with the text the mask hides
        self._highlighter: Callable[[str], _TagMarkup] | None = None
        self._highlight_runs: list[tuple[Hashable, int]] | None = None
        self._highlight_ready = False
        self._text_completer = text_completer
        # (candidates, index) of the completion cycle, where candidate 0 is the text and position it started from
        self._completion_cycle: tuple[tuple[tuple[str | bytes, int], ...], int] | None = None
        # text and position the last completion step left, which a change from elsewhere no longer matches
        self._completion_applied: tuple[str | bytes, int] | None = None
        # True while a text or cursor change does not end the completion cycle: during a completion step,
        # and inside set_edit_text(), which ends it itself once its signals are sent
        self._completion_hold = False
        self._undo_stack: deque[tuple[str | bytes, int]] = deque(maxlen=0)
        self._redo_stack: deque[tuple[str | bytes, int]] = deque(maxlen=0)
        # depth of the editing transaction: a key, or undo() and redo(); set_edit_text() outside it clears the history
        self._edit_depth = 0
        # text and cursor position when the transaction started, None when it records no undo step
        self._undo_before: tuple[str | bytes, int] | None = None
        # kind of the change the key in the transaction made, when a run of such keys is one undo step
        self._undo_kind: Literal["insert", "backspace", "delete"] | None = None
        # (kind, text, position) after the last undo step, which a key of the same kind from there continues
        self._undo_run: tuple[str, str | bytes, int] | None = None
        self.undo_limit = undo_limit
        self._kill_buffer = kill_buffer
        # (length of the kill buffer, entry) after the last kill, while the next kill joins that entry
        self._kill_last: tuple[int, str | bytes] | None = None
        # True when the key in the editing transaction killed text, so that the chain of kills goes on
        self._kill_now = False
        self.set_edit_text(edit_text)
        if edit_pos is None:
            edit_pos = len(edit_text)
        self.set_edit_pos(edit_pos)
        self.set_mask(mask)
        self.highlighter = highlighter

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
            "placeholder": self._placeholder,
        }
        return remove_defaults(attrs, Edit.__init__)


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
        with self._editing():  # the strip belongs to the undo step of the key
            max_digits = sys.get_int_max_str_digits()  # 0 means no limit
            if max_digits and self.valid_char(key) and len(self.insert_text_result(key)[0]) > max_digits:
                return key

            if unhandled := super().keypress(size, key):
                return unhandled
            if self._command_map[key] in {Command.UNDO, Command.REDO}:
                return None  # a restored state is kept as it was shown

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

    def _valid_insert(self, text: str | bytes, result_text: str | bytes) -> bool:
        """Return whether *result_text* is decimal digits, no more than :func:`sys.get_int_max_str_digits` allows."""
        if isinstance(result_text, bytes):
            result_text = result_text.decode("ascii", "replace")  # a replaced byte is not a digit
        max_digits = sys.get_int_max_str_digits()  # 0 means no limit
        return all(char in string.digits for char in result_text) and not (max_digits and len(result_text) > max_digits)

    def _completion_candidate(self, text: str | bytes, pos: int) -> tuple[str | bytes, int]:
        """Return a completer's replacement as the edit would hold it.

        The leading zeros :meth:`keypress` removes are removed here already.
        The cycle then records the text a completion key leaves, so the next key continues it.
        """
        return self._strip_leading_zeros(*super()._completion_candidate(text, pos))

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
