"""Edit: a text editing widget, and IntEdit for integers."""

from __future__ import annotations

import contextlib
import string
import sys
import typing
import unicodedata
from collections.abc import Iterable

from urwid import text_layout
from urwid.canvas import CompositeCanvas, apply_text_layout
from urwid.command_map import Command
from urwid.split_repr import remove_defaults
from urwid.str_util import _grapheme_boundary, calc_width, is_wide_char, move_next_char, move_prev_char
from urwid.util import decompose_tagmarkup

from .attr_map import _attr_map_dict
from .constants import Align, Severity, Sizing, ValidationMessage, WrapMode
from .text import Text, TextError
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping, Sequence
    from typing import Literal

    from urwid.canvas import TextCanvas
    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike


class EditError(TextError):
    """Edit related errors."""


def _validation_messages(
    result: ValidationMessage | str | Iterable[ValidationMessage] | None,
) -> tuple[ValidationMessage, ...]:
    """Return what a validator returned as a tuple of messages.

    :raises TypeError: *result* is not ``None``, a :class:`str`, a :class:`ValidationMessage`,
        or an iterable of :class:`ValidationMessage`.
        A message's severity is not a :class:`Severity` member.
    """
    if result is None:
        return ()
    if isinstance(result, str):
        return (ValidationMessage(Severity.ERROR, result),)
    if isinstance(result, ValidationMessage):
        messages: tuple[object, ...] = (result,)
    elif isinstance(result, (bytes, bytearray)) or not isinstance(result, Iterable):
        detail = f"a validator returned {result!r}, not a message, messages or None"
        raise TypeError(detail)
    else:
        messages = tuple(result)
    for message in messages:
        if not isinstance(message, ValidationMessage) or not isinstance(message.severity, Severity):
            detail = f"a validator returned {message!r}, not a ValidationMessage with a Severity"
            raise TypeError(detail)
    return typing.cast("tuple[ValidationMessage, ...]", messages)


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
    * ``"validation"`` is sent when :attr:`validation` changes.
      It receives the old and the new value as arguments.
    * ``"completions"`` is sent when a completion cycle starts, moves or ends, see :attr:`completer`.
      It receives the new value of :attr:`completions` as an argument.
    """

    _sizing = frozenset([Sizing.FLOW])
    _selectable = True
    ignore_focus = False
    # (this variable is picked up by the MetaSignals metaclass)
    signals: typing.ClassVar[list[str]] = ["change", "postchange", "submit", "validation", "completions"]

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
        placeholder: _TagMarkup | None = None,
        placeholder_grow: bool | None = None,
        validator: Callable[[str], ValidationMessage | str | Iterable[ValidationMessage] | None] | None = None,
        validation_attr: Mapping[Severity, _AttrMapLike] | None = None,
        validation_focus_attr: Mapping[Severity, _AttrMapLike] | None = None,
        completer: Callable[[str, int], Sequence[tuple[str, int]]] | None = None,
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
        :param completer: called with :attr:`edit_text` and :attr:`edit_pos` for the completions, see :attr:`completer`
        :raises ValueError: *max_length* is negative, or *edit_text* is longer than it.
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
        self._validation_attr = self._severity_attr_maps(validation_attr)
        self._validation_focus_attr = self._severity_attr_maps(validation_focus_attr)
        self._completer = completer
        # (candidates, index) of the completion cycle, where candidate 0 is the text and position it started from
        self._completions: tuple[tuple[tuple[str | bytes, int], ...], int] | None = None
        # text and position the last completion step left, which a change from elsewhere no longer matches
        self._completion_applied: tuple[str | bytes, int] | None = None
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

    @property
    def validator(self) -> Callable[[str], ValidationMessage | str | Iterable[ValidationMessage] | None] | None:
        """Callable that checks the whole :attr:`edit_text`, or ``None`` for no check.

        It is called with the edit text and returns its findings:

        - ``None`` or an empty iterable when the text is valid;
        - a :class:`str`, which is an error message;
        - a :class:`ValidationMessage`;
        - an iterable of :class:`ValidationMessage`.

        It is called once by each :meth:`set_edit_text` call, after ``"postchange"``,
        when it is assigned, and by :meth:`validate`, never while rendering.
        A subclass whose :meth:`set_edit_text` does not call this class's method calls :meth:`validate` itself.
        The result is :attr:`validation`.
        Keys, focus and ``"submit"`` do not depend on it: an application reads :attr:`validation` to refuse a value.

        >>> e = Edit("Port: ", validator=lambda text: None if text.isdecimal() else "not a number")
        >>> e.validation
        (ValidationMessage(severity=<Severity.ERROR: 3>, message='not a number'),)
        >>> e.keypress((20,), "8")
        >>> e.validation
        ()
        >>> e.validator = lambda text: ValidationMessage(Severity.WARNING, "privileged") if int(text) < 1024 else None
        >>> e.severity
        <Severity.WARNING: 2>

        :raises TypeError: on assignment, the validator returned something else than the types above;
            the previous validator is kept.
        """
        return self._validator

    @validator.setter
    def validator(
        self,
        validator: Callable[[str], ValidationMessage | str | Iterable[ValidationMessage] | None] | None,
    ) -> None:
        previous, self._validator = self._validator, validator
        try:
            self.validate()
        except TypeError:
            self._validator = previous
            raise

    @property
    def validation(self) -> tuple[ValidationMessage, ...]:
        """Findings of :attr:`validator` for the current :attr:`edit_text`; empty when valid or without a validator."""
        return self._validation

    @property
    def severity(self) -> Severity | None:
        """The worst :class:`Severity` in :attr:`validation`, or ``None`` when it is empty."""
        return max(message.severity for message in self._validation) if self._validation else None

    def validate(self) -> tuple[ValidationMessage, ...]:
        """Run :attr:`validator` on :attr:`edit_text` now and return the new :attr:`validation`.

        This is for a check that depends on something else than the text, which has changed.
        ``"validation"`` is sent when the result differs from the previous one.

        :raises TypeError: the validator returned something else than the types :attr:`validator` lists;
            :attr:`validation` is left as it was.
        """
        validation = () if self._validator is None else _validation_messages(self._validator(self._edit_text))
        if validation != self._validation:
            old_validation, self._validation = self._validation, validation
            self._invalidate()
            self._emit("validation", old_validation, validation)
        return self._validation  # a "validation" handler may have changed the text, and validated it again

    @staticmethod
    def _severity_attr_maps(
        attr_maps: Mapping[Severity, _AttrMapLike] | None,
    ) -> dict[Severity, dict[Hashable, Hashable]]:
        """Return *attr_maps* with each value as an attribute mapping dictionary.

        :raises AttrMapError: a key or value of an attribute map is not hashable.
        """
        return {} if attr_maps is None else {severity: _attr_map_dict(m) for severity, m in attr_maps.items()}

    @property
    def validation_attr(self) -> dict[Severity, dict[Hashable, Hashable]]:
        """Attribute map applied to the rendered edit for each :attr:`severity`.

        It is set from a mapping of :class:`Severity` to what :class:`AttrMap` takes as its attribute map, or ``None``.
        A single attribute is stored as ``{None: attribute}``, so the caption's own attributes are placed over it.
        A severity with no entry is not coloured.
        A copy is returned.

        >>> e = Edit(validator=lambda text: "empty" if not text else None, validation_attr={Severity.ERROR: "error"})
        >>> next(iter(e.render((4,)).content()))
        [('error', None, b'    ')]
        """
        return {severity: attr_map.copy() for severity, attr_map in self._validation_attr.items()}

    @validation_attr.setter
    def validation_attr(self, attr_maps: Mapping[Severity, _AttrMapLike] | None) -> None:
        self._validation_attr = self._severity_attr_maps(attr_maps)
        self._invalidate()

    @property
    def validation_focus_attr(self) -> dict[Severity, dict[Hashable, Hashable]]:
        """Attribute map applied to the rendered edit for each :attr:`severity` while it is focused.

        It is set as :attr:`validation_attr`.
        A severity with no entry here uses its :attr:`validation_attr` entry when focused.
        A copy is returned.
        """
        return {severity: attr_map.copy() for severity, attr_map in self._validation_focus_attr.items()}

    @validation_focus_attr.setter
    def validation_focus_attr(self, attr_maps: Mapping[Severity, _AttrMapLike] | None) -> None:
        self._validation_focus_attr = self._severity_attr_maps(attr_maps)
        self._invalidate()

    @property
    def completer(self) -> Callable[[str, int], Sequence[tuple[str, int]]] | None:
        """Callable that returns the completions of :attr:`edit_text`, or ``None`` for no completion.

        It is called with the edit text and the cursor position.
        It returns whole replacements, each a ``(text, position)`` pair, and decides itself what is completed.
        A replacement equal to the current text and position is left out.

        Keys that complete:

        - :kbd:`tab` and :kbd:`shift tab`, unless :attr:`allow_tab` is set;
        - the ``'complete next'`` and ``'complete previous'`` commands, which no key is mapped to by default.

        A completion key with no cycle running calls the completer:

        - when it returns nothing, the key is returned, so that focus navigation still works;
        - when it returns one replacement, that replacement is applied and no cycle starts,
          so the next completion key calls the completer again from the new text;
        - when it returns several, a cycle starts with the first replacement, or the last one for
          ``'complete previous'``.

        A completer that returns the common prefix of several matches as its one replacement, and the matches once
        the prefix is complete, inserts the prefix first and then cycles through the matches.
        Further completion keys step through the replacements and back to the text the cycle started from.
        Any other key ends the cycle.
        A change of the text or the cursor made from elsewhere ends it at the next completion key,
        which then calls the completer again.
        Each step sets the text, so :attr:`validator` runs once per step.
        Setting the completer ends the cycle.

        >>> words = ["alpha", "alpine", "beta"]
        >>> def complete(text, pos):
        ...     return [(w, len(w)) for w in words if w.startswith(text[:pos])]
        >>> e = Edit("", "al", completer=complete)
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        alpha
        >>> e.keypress((20,), "tab")
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        al
        >>> Edit("", "x", completer=complete).keypress((20,), "tab")
        'tab'
        >>> e = Edit("", "b", completer=complete)
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        beta
        >>> e.keypress((20,), "tab")
        'tab'
        """
        return self._completer

    @completer.setter
    def completer(self, completer: Callable[[str, int], Sequence[tuple[str, int]]] | None) -> None:
        self._completer = completer
        self._end_completion()

    @property
    def completions(self) -> tuple[tuple[tuple[str | bytes, int], ...], int] | None:
        """``(candidates, index)`` while a completion cycle runs, ``None`` otherwise.

        A completer result with one replacement starts no cycle.

        *candidates* holds ``(text, position)`` pairs.
        The first one is the text and cursor position the cycle started from, the others are what :attr:`completer`
        returned, converted to the type of the caption.
        *index* is the candidate the edit shows now.
        """
        return self._completions

    def _end_completion(self) -> None:
        """End the completion cycle, sending ``"completions"`` when one was running."""
        if self._completions is None:
            return
        self._completions = None
        self._completion_applied = None
        self._emit("completions", None)

    def _completion_step(self, key: str) -> int:
        """Return 1 when *key* completes forward, -1 when it completes backward, 0 otherwise."""
        if self._completer is None:
            return 0
        command = self._command_map[key]
        if command == Command.COMPLETE_NEXT or (key == "tab" and not self.allow_tab):
            return 1
        if command == Command.COMPLETE_PREVIOUS or (key == "shift tab" and not self.allow_tab):
            return -1
        return 0

    def _complete(self, step: int) -> bool:
        """Apply the next completion candidate in the direction of *step*, calling the completer when no cycle runs.

        :returns: whether a candidate was applied; ``False`` when the completer returned nothing but the current text
            and position.
        :raises ValueError: a candidate is longer than :attr:`max_length`; the text and the cycle are left as they
            were.
        """
        if self._completions is not None and (self._edit_text, self._edit_pos) != self._completion_applied:
            self._end_completion()
        if self._completions is None:
            completer = typing.cast("Callable[[str, int], Sequence[tuple[str, int]]]", self._completer)
            current = (self._edit_text, self._edit_pos)
            results = []
            for text, pos in completer(self._edit_text, self._edit_pos):
                candidate_text = self._normalize_to_caption(text)
                # the position the cursor takes, see set_edit_pos(), so that a candidate equal to the current text
                # and cursor is left out
                candidate = (
                    candidate_text,
                    _grapheme_boundary(candidate_text, min(max(pos, 0), len(candidate_text)), forward=False),
                )
                if candidate != current:
                    results.append(candidate)
            if not results:
                return False
            for result_text, _pos in results:
                if self._max_length is not None and len(result_text) > self._max_length:
                    detail = f"completion of length {len(result_text)} is longer than max_length {self._max_length}"
                    raise ValueError(detail)
            if len(results) == 1:
                self._set_edit_text_and_pos(*results[0])
                return True
            candidates: tuple[tuple[str | bytes, int], ...] = (current, *results)
            index = 0
        else:
            candidates, index = self._completions
        index = (index + step) % len(candidates)
        self._set_edit_text_and_pos(*candidates[index])
        # read back: an override or a "postchange" handler may have changed what was applied
        self._completions = (candidates, index)
        self._completion_applied = (self._edit_text, self._edit_pos)
        self._emit("completions", self._completions)
        return True

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
        :raises TypeError: :attr:`validator` returned something else than the types it lists;
            the text is changed already.

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
        self.validate()
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

        A key that completes steps the completion cycle, and any other key ends it, see :attr:`completer`.

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
            A completion is longer than :attr:`max_length`.
        """
        if not (complete_step := self._completion_step(key)):
            self._end_completion()

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

        if complete_step:
            return None if self._complete(complete_step) else key

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
        if (placeholder := self._placeholder_layout(maxcol)) is not None:
            text, attr, trans = placeholder
        else:
            text, attr = self.get_text()
            trans = self.get_line_translation(maxcol, (text, attr))
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

        # .. will need to FIXME if I want highlight to work again
        # if self.highlight:
        #    hstart, hstop = self.highlight_coords()
        #    d.coords['highlight'] = [ hstart, hstop ]
        return canv

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        r"""Return the number of rows the rendered edit requires, including a :attr:`placeholder` that grows it.

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
        caption_attrib = self._attrib.copy()
        if (uncovered := len(self._caption) - sum(run for _attr, run in caption_attrib)) > 0:
            caption_attrib.append((None, uncovered))  # so that the placeholder's attributes start after the caption
        attrib = [*caption_attrib, *placeholder_attrib]

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
