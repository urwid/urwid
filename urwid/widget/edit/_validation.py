"""Validation layer of :class:`Edit`."""

from __future__ import annotations

import typing
from collections.abc import Iterable

from ..attr_map import _attr_map_dicts
from ..constants import Severity, ValidationMessage
from ..text import Text
from ..widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping

    from ..attr_map import _AttrMapLike


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


class _EditValidation(WidgetWrap[Text]):
    """Validator, validation result and its colours of :class:`Edit`."""

    _edit_text: str
    _validation: tuple[ValidationMessage, ...]
    _validation_attr: dict[Severity, dict[Hashable, Hashable]]
    _validation_focus_attr: dict[Severity, dict[Hashable, Hashable]]
    _validator: Callable[[str], ValidationMessage | str | Iterable[ValidationMessage] | None] | None

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
        A subclass whose :meth:`set_edit_text` does not call this class's method calls ``Edit.validate(self)`` itself,
        which a :meth:`validate` of its own does not replace.
        The result is :attr:`validation`.
        Keys, focus, ``"submit"`` and ``"cancel"`` do not depend on it.
        An application reads :attr:`validation` to refuse a value.

        >>> from urwid import Edit
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
            self._run_validator()
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
        This class never calls it, so a subclass may define its own :meth:`validate` for something else.

        :raises TypeError: the validator returned something else than the types :attr:`validator` lists;
            :attr:`validation` is left as it was.
        """
        return self._run_validator()

    def _run_validator(self) -> tuple[ValidationMessage, ...]:
        """Store and return the result of :attr:`validator` as :attr:`validation`.

        This is what :meth:`validate` runs.
        A validator that changed the text or replaced itself has its result discarded unchecked.
        The nested :meth:`set_edit_text` or :attr:`validator` assignment already stored the current result.
        """
        validator, text = self._validator, self._edit_text
        result = None if validator is None else validator(text)
        if self._validator is not validator or self._edit_text != text:
            return self._validation
        validation = _validation_messages(result)
        if validation != self._validation:
            old_validation, self._validation = self._validation, validation
            self._invalidate()
            self._emit("validation", old_validation, validation)
        return self._validation  # a "validation" handler may have changed the text, and validated it again

    @property
    def validation_attr(self) -> dict[Severity, dict[Hashable, Hashable]]:
        """Attribute map applied to the rendered edit for each :attr:`severity`.

        It is set from a mapping of :class:`Severity` to what :class:`AttrMap` takes as its attribute map, or ``None``.
        A single attribute is stored as ``{None: attribute}``, so the caption's own attributes are placed over it.
        A severity with no entry is not coloured.
        A copy is returned.

        >>> from urwid import Edit
        >>> e = Edit(validator=lambda text: "empty" if not text else None, validation_attr={Severity.ERROR: "error"})
        >>> next(iter(e.render((4,)).content()))
        [('error', None, b'    ')]
        """
        return {severity: attr_map.copy() for severity, attr_map in self._validation_attr.items()}

    @validation_attr.setter
    def validation_attr(self, attr_maps: Mapping[Severity, _AttrMapLike] | None) -> None:
        self._validation_attr = _attr_map_dicts(attr_maps)
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
        self._validation_focus_attr = _attr_map_dicts(attr_maps)
        self._invalidate()
