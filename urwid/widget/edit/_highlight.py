"""Colouring layer of :class:`Edit`: attribute runs of the edit text by its content."""

from __future__ import annotations

import typing

from urwid.util import decompose_tagmarkup

from ..text import Text
from ..widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable

    from urwid.util import _TagMarkup

    from ..constants import Severity


class _EditHighlight(WidgetWrap[Text]):
    """Explicit attribute runs and the highlighter of :class:`Edit`, and when they are drawn."""

    _edit_text: str
    _mask: str | None
    _validation_attr: dict[Severity, dict[Hashable, Hashable]]
    _validation_focus_attr: dict[Severity, dict[Hashable, Hashable]]
    # explicit runs over the edit text, set through edit_attrib
    _edit_attrib: list[tuple[Hashable, int]]
    _highlighter: Callable[[str], _TagMarkup] | None
    # runs the highlighter returned for the current text and validation, None until it is called for them
    _highlight_runs: list[tuple[Hashable, int]] | None
    # True once the validation of the current text has succeeded, so that the highlighter may be called for it
    _highlight_ready: bool

    @property
    def edit_attrib(self) -> list[tuple[Hashable, int]]:
        """Display attributes of :attr:`edit_text`, as run-length encoded ``(attribute, length)`` pairs.

        They have the form of :attr:`Text.attrib`, counted from the start of the edit text.
        A length counts code points of a :class:`str` edit text and bytes of a :class:`bytes` one.
        Runs that cover less than the whole text leave the rest uncoloured.
        The runs belong to one text: a change of :attr:`edit_text` clears them.
        Assigning ``[]`` clears them.
        :attr:`highlighter` then colours the text again.
        ``[(None, len(edit_text))]`` draws the text uncoloured while a highlighter is set.
        They are not drawn while :attr:`edit_text` is empty or :attr:`mask` is set.
        Assigning them invalidates the widget and sends no signal.
        A copy is returned and a copy is stored.
        They are unrelated to :attr:`highlight`, the selected range, which :attr:`select_attr` draws over them.

        They colour parts of the text.
        :attr:`validation_attr` and :attr:`validation_focus_attr` colour the whole text,
        so they cannot be set together with the runs.
        A highlighter can colour an error itself from :attr:`validation`.

        >>> from urwid import Edit
        >>> e = Edit("$ ", "ls -l")
        >>> e.edit_attrib = [("command", 2), (None, 1), ("option", 2)]
        >>> e.attrib
        [(None, 2), ('command', 2), (None, 1), ('option', 2)]

        :raises ValueError: on assignment, a length is negative, or the lengths add up to more than :attr:`edit_text`.
            The runs are not empty and :attr:`validation_attr` or :attr:`validation_focus_attr` is set.
        """
        return self._edit_attrib.copy()

    @edit_attrib.setter
    def edit_attrib(self, runs: Iterable[tuple[Hashable, int]]) -> None:
        runs = list(runs)
        if any(length < 0 for _attr, length in runs):
            raise ValueError(f"edit_attrib {runs!r} has a negative length")
        if (total := sum(length for _attr, length in runs)) > len(self._edit_text):
            raise ValueError(f"edit_attrib covers {total} characters of an edit text of {len(self._edit_text)}")
        self._check_colouring(highlights=bool(runs) or self._highlighter is not None)
        self._edit_attrib = runs
        self._invalidate()

    @property
    def highlighter(self) -> Callable[[str], _TagMarkup] | None:
        """Callable that returns :attr:`edit_text` as text markup, coloured by its content, or ``None``.

        It is called with the edit text and returns markup of the same text, as :class:`Text` takes it.
        Its runs are drawn while :attr:`edit_attrib` is empty.
        It is called when the widget is drawn or :meth:`get_text` is called.
        It is called at most once for each text and :attr:`validation`.
        A cursor move, a focus change or a redraw at another size does not call it again.
        It is not called while :attr:`edit_text` is empty or :attr:`mask` is set.
        After a change of the text it is not called until the validation of the new text has run,
        so :attr:`validation` is always the one of the text it is given.
        :meth:`rehighlight` calls it again for a highlighter that depends on something else than the text.

        It colours parts of the text.
        :attr:`validation_attr` and :attr:`validation_focus_attr` colour the whole text,
        so they cannot be set together with a highlighter.
        It is unrelated to :attr:`highlight`, the selected range, which :attr:`select_attr` draws over its runs.

        >>> from urwid import Edit
        >>> e = Edit("$ ", "ls -l", highlighter=lambda text: [("command", text[:2]), text[2:]])
        >>> e.attrib
        [(None, 2), ('command', 2)]

        :raises ValueError: on assignment, a highlighter is set while :attr:`validation_attr`
            or :attr:`validation_focus_attr` is set.
            When drawn, the text of the returned markup differs from :attr:`edit_text`.
        """
        return self._highlighter

    @highlighter.setter
    def highlighter(self, highlighter: Callable[[str], _TagMarkup] | None) -> None:
        self._check_colouring(highlights=highlighter is not None or bool(self._edit_attrib))
        self._highlighter = highlighter
        self._highlight_runs = None
        self._invalidate()

    def rehighlight(self) -> None:
        """Call :attr:`highlighter` again the next time the widget is drawn.

        This is for a highlighter that depends on something else than the text, which has changed.
        """
        self._highlight_runs = None
        self._invalidate()

    def _check_colouring(self, *, highlights: bool | None = None, colours_validation: bool | None = None) -> None:
        """Refuse a highlighter or explicit runs together with validation colours.

        An argument left ``None`` is taken from the current state.

        :param highlights: a highlighter or non-empty :attr:`edit_attrib` is set.
        :param colours_validation: :attr:`validation_attr` or :attr:`validation_focus_attr` is not empty.
        :raises ValueError: both are set.
        """
        if highlights is None:
            highlights = self._highlighter is not None or bool(self._edit_attrib)
        if colours_validation is None:
            colours_validation = bool(self._validation_attr or self._validation_focus_attr)
        if highlights and colours_validation:
            raise ValueError(
                "validation_attr and validation_focus_attr colour the whole edit text, "
                "highlighter and edit_attrib colour parts of it: only one of the two can be set"
            )

    def _highlight_text_changed(self) -> None:
        """Drop the runs of the previous text.

        The highlighter is deferred until the new text is validated.
        """
        self._edit_attrib = []
        self._highlight_runs = None
        self._highlight_ready = False

    def _highlight_validated(self, changed: bool) -> None:
        """Allow the highlighter for the current text, whose validation has just been stored.

        :param changed: the validation differs from the previous one, so the kept runs are dropped.
        """
        if changed:
            self._highlight_runs = None
        if changed or not self._highlight_ready:
            self._highlight_ready = True
            self._invalidate()

    def _edit_runs(self) -> list[tuple[Hashable, int]]:
        """Return the attribute runs to draw over the edit text, or ``[]`` for none.

        :raises ValueError: the text of the markup the highlighter returned differs from :attr:`edit_text`.
        """
        if self._mask is not None or not self._edit_text:
            return []
        if self._edit_attrib:
            return self._edit_attrib
        if self._highlighter is None or not self._highlight_ready:
            return []
        if self._highlight_runs is None:
            text, runs = decompose_tagmarkup(self._highlighter(self._edit_text))
            if text != self._edit_text:
                raise ValueError(f"highlighter returned markup of {text!r} for the edit text {self._edit_text!r}")
            self._highlight_runs = runs
        return self._highlight_runs
