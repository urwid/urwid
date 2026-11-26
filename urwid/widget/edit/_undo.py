"""Undo, redo and kill buffer layer of :class:`Edit`."""

from __future__ import annotations

import contextlib
import typing
from collections import deque

from ._text import _EditText

if typing.TYPE_CHECKING:
    from collections.abc import Generator, MutableSequence
    from typing import Literal


class _EditUndo(_EditText):
    """Undo and redo history and the kill buffer of :class:`Edit`."""

    _kill_buffer: MutableSequence[str | bytes] | None
    _kill_now: bool
    _undo_kind: Literal["insert", "backspace", "delete"] | None

    @property
    def kill_buffer(self) -> MutableSequence[str | bytes] | None:
        """The list that the readline word and line delete commands put the deleted text into, or ``None`` for none.

        The application creates the list, and several edits may share it.
        Deleted text joins the newest entry while the deletes follow one another in this edit, as in readline:
        text deleted forward is appended to it, text deleted backward is put before it.
        Any other key, a mouse event, a change from elsewhere, or a change of the list made by someone else
        starts a new entry.
        A masked edit puts nothing into the list.
        :kbd:`backspace`, :kbd:`delete` and ``'delete char right'`` delete without putting the text into the list.

        The ``'yank'`` command, which no key is mapped to by default, inserts the newest entry at the cursor.
        The entry is not inserted, and the key is returned, when the keys of this edit could not type the result:
        a newline in an edit without :attr:`multiline`, a letter in an :class:`IntEdit`, text that makes
        :attr:`edit_text` longer than :attr:`max_length`.

        >>> from urwid import Edit
        >>> from urwid import CommandMap
        >>> class ReadlineEdit(Edit):
        ...     _command_map = CommandMap()
        ...     _command_map.bind_readline()
        >>> kills = []
        >>> e = ReadlineEdit("", "one two three", kill_buffer=kills)
        >>> e.keypress((20,), "ctrl w")
        >>> e.keypress((20,), "ctrl w")
        >>> kills
        ['two three']
        >>> e.keypress((20,), "ctrl y")
        >>> print(e.edit_text)
        one two three
        """
        return self._kill_buffer

    @kill_buffer.setter
    def kill_buffer(self, kill_buffer: MutableSequence[str | bytes] | None) -> None:
        self._kill_buffer = kill_buffer
        self._kill_last = None

    def _kill(self, text: str | bytes, *, forward: bool) -> None:
        """Put *text*, which a delete command removed, into :attr:`kill_buffer`.

        It joins the entry of the previous kill when that entry is still the newest one this edit put in.
        """
        buffer = self._kill_buffer
        if buffer is None or self._mask is not None:
            return
        last = self._kill_last
        if last is not None and len(buffer) == last[0] and buffer[-1] is last[1]:
            entry = last[1] + text if forward else text + last[1]  # type: ignore[operator]  # one edit, one type
            buffer[-1] = entry
        else:
            entry = text
            buffer.append(entry)
        self._kill_last = (len(buffer), entry)
        self._kill_now = True

    def _yank(self) -> bool:
        """Insert the newest entry of :attr:`kill_buffer` at the cursor, unless the keys could not type the result.

        :returns: whether the entry was inserted.
        """
        if not self._kill_buffer:
            return False
        try:
            text = self._normalize_to_caption(self._kill_buffer[-1])
        except UnicodeError:
            return False
        result_text, _result_pos = self.insert_text_result(text)  # type: ignore[arg-type]  # normalised to the caption
        if self._max_length is not None and len(result_text) > self._max_length:
            return False
        if not self._valid_insert(text, result_text):
            return False
        self.insert_text(text)  # type: ignore[arg-type]  # normalised to the caption
        return True

    @property
    def undo_limit(self) -> int:
        """The number of changes :meth:`undo` can take back, 0 for no undo history.

        A change is what a key does to the text, through :meth:`keypress`.
        Consecutive typed characters are one change, and so is a run of :kbd:`backspace` or of :kbd:`delete`.
        A change from elsewhere, through :meth:`set_edit_text` or :meth:`insert_text`, clears the history,
        so that a reused edit does not bring back an earlier value.
        Lowering the limit drops the oldest changes, and 0 clears the history.
        The ``'undo'`` and ``'redo'`` commands, which no key is mapped to by default, call :meth:`undo` and
        :meth:`redo`.

        >>> from urwid import Edit
        >>> e = Edit(undo_limit=10)
        >>> for key in "one two":
        ...     e.keypress((20,), key)
        >>> e.keypress((20,), "backspace")
        >>> e.undo()
        True
        >>> print(e.edit_text)
        one two
        >>> e.undo()
        True
        >>> print(e.edit_text)
        <BLANKLINE>
        >>> e.redo()
        True
        >>> print(e.edit_text)
        one two

        :raises ValueError: on assignment, the limit is negative.
        """
        return typing.cast("int", self._undo_stack.maxlen)

    @undo_limit.setter
    def undo_limit(self, undo_limit: int) -> None:
        if undo_limit < 0:
            raise ValueError(f"undo_limit must not be negative, got {undo_limit}")
        self._undo_stack = deque(self._undo_stack, maxlen=undo_limit)
        self._redo_stack = deque(self._redo_stack, maxlen=undo_limit)
        self._undo_run = None  # a run typed while the limit was 0 has no step to continue

    def undo(self) -> bool:
        """Take back the last change, restoring the text and the cursor position from before it.

        See :attr:`undo_limit`.
        The text goes through :meth:`set_edit_text`, so signals and :attr:`validator` run as for any change.

        :returns: whether the text changed; ``False`` when there is nothing to undo, or the text to restore is
            longer than :attr:`max_length`.
        :raises Exception: what :meth:`set_edit_text` raises for the restored text.
            When it raises before changing the text, the history is left as it was.
        """
        return self._undo_step(self._undo_stack, self._redo_stack)

    def redo(self) -> bool:
        """Make the last change :meth:`undo` took back again.

        Any new change clears what there is to redo.

        :returns: whether the text changed; ``False`` when there is nothing to redo, or the text to restore is
            longer than :attr:`max_length`.
        :raises Exception: what :meth:`set_edit_text` raises for the restored text.
            When it raises before changing the text, the history is left as it was.
        """
        return self._undo_step(self._redo_stack, self._undo_stack)

    def _undo_step(
        self,
        source: deque[tuple[str | bytes, int]],
        target: deque[tuple[str | bytes, int]],
    ) -> bool:
        """Restore the newest state of *source*, and keep the current state on *target*.

        A restored state is one the edit showed before, so it is restored as it is, with no further normalisation.
        The step is moved once the text has changed, also when a ``"postchange"`` handler or the validator raises.
        """
        if not source:
            return False
        text, pos = source[-1]
        if self._max_length is not None and len(text) > self._max_length:
            return False
        current = (self._edit_text, self._edit_pos)
        self._edit_depth += 1
        try:
            self._set_edit_text_and_pos(text, pos)
        finally:
            self._edit_depth -= 1
            self._undo_before = None  # a key that undoes records no step of its own
            self._undo_run = self._kill_last = None
            if self._edit_text != current[0]:
                source.pop()
                target.append(current)
        return self._edit_text != current[0]

    @contextlib.contextmanager
    def _editing(self) -> Generator[None]:
        """Run the body as one editing transaction, which records one undo step when it changed the text.

        Transactions nest, and the outermost one records the step.
        A subclass whose :meth:`keypress` changes the text after calling this class's method holds it around its
        whole body, so that its change belongs to the step of the key.
        """
        if not self._edit_depth:
            self._undo_before = (self._edit_text, self._edit_pos)
            self._undo_kind = None
            self._kill_now = False
        self._edit_depth += 1
        try:
            yield
        finally:
            self._edit_depth -= 1
            if not self._edit_depth:
                if not self._kill_now:
                    self._kill_last = None  # any other key ends the chain of kills
                before, self._undo_before = self._undo_before, None
                kind, self._undo_kind = self._undo_kind, None
                if before is None or before[0] == self._edit_text:
                    self._undo_run = None
                else:
                    if kind is None or self._undo_run != (kind, *before):
                        self._undo_stack.append(before)
                    self._redo_stack.clear()
                    self._undo_run = None if kind is None else (kind, self._edit_text, self._edit_pos)
