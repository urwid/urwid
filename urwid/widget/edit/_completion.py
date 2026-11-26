"""Completion state layer of :class:`Edit`."""

from __future__ import annotations

import typing

from urwid.command_map import Command

from ._validation import _EditValidation

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class _EditCompletionState(_EditValidation):
    """Text completer and the state of a completion cycle of :class:`Edit`."""

    _completion_applied: tuple[str | bytes, int] | None
    _completion_cycle: tuple[tuple[tuple[str | bytes, int], ...], int] | None
    _text_completer: Callable[[str, int], Sequence[tuple[str, int]]] | None
    allow_tab: bool

    @property
    def text_completer(self) -> Callable[[str, int], Sequence[tuple[str, int]]] | None:
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
        Any other key ends the cycle, and so does a change of the text or the cursor made from elsewhere.
        Each step sets the text, so :attr:`validator` runs once per step.
        Setting the completer ends the cycle.

        A step applies a replacement through :meth:`set_edit_text`.
        An override may raise there for a replacement it does not accept, before it changes the text.
        The exception then leaves :meth:`keypress`.
        The cycle stays where it was.
        The next completion key tries the same replacement again.
        A completer for such a subclass returns only replacements the subclass accepts.

        >>> from urwid import Edit
        >>> words = ["alpha", "alpine", "beta"]
        >>> def complete(text, pos):
        ...     return [(w, len(w)) for w in words if w.startswith(text[:pos])]
        >>> e = Edit("", "al", text_completer=complete)
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        alpha
        >>> e.keypress((20,), "tab")
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        al
        >>> Edit("", "x", text_completer=complete).keypress((20,), "tab")
        'tab'
        >>> e = Edit("", "b", text_completer=complete)
        >>> e.keypress((20,), "tab")
        >>> print(e.edit_text)
        beta
        >>> e.keypress((20,), "tab")
        'tab'
        """
        return self._text_completer

    @text_completer.setter
    def text_completer(self, text_completer: Callable[[str, int], Sequence[tuple[str, int]]] | None) -> None:
        self._text_completer = text_completer
        self._end_completion()

    @property
    def completion_cycle(self) -> tuple[tuple[tuple[str | bytes, int], ...], int] | None:
        """``(candidates, index)`` while a completion cycle runs, ``None`` otherwise.

        A completer result with one replacement starts no cycle.

        *candidates* holds ``(text, position)`` pairs.
        The first one is the text and cursor position the cycle started from, the others are what :attr:`text_completer`
        returned, converted to the type of the caption.
        *index* is the candidate the edit shows now.
        """
        return self._completion_cycle

    def _end_completion(self) -> None:
        """End the completion cycle, sending ``"completion_cycle"`` when one was running."""
        if self._completion_cycle is None:
            return
        self._completion_cycle = None
        self._completion_applied = None
        self._emit("completion_cycle", None)

    def _completion_direction(self, key: str) -> int:
        """Return 1 when *key* completes forward, -1 when it completes backward, 0 otherwise."""
        if self._text_completer is None:
            return 0
        command = self._command_map[key]
        if command == Command.COMPLETE_NEXT or (key == "tab" and not self.allow_tab):
            return 1
        if command == Command.COMPLETE_PREVIOUS or (key == "shift tab" and not self.allow_tab):
            return -1
        return 0
