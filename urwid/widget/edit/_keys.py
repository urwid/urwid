"""Key handling layer of :class:`Edit`."""

from __future__ import annotations

import typing

from urwid import text_layout
from urwid.command_map import Command
from urwid.str_util import _grapheme_boundary, calc_width, move_next_char, move_prev_char

from ..constants import Align
from ._render import _EditRender

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class _EditKeys(_EditRender):
    """Key handling and completion steps of :class:`Edit`."""

    expand_tabs: bool

    def _step_completion(self, step: int) -> bool:
        """Apply the next completion candidate in the direction of *step*, calling the completer when no cycle runs.

        :returns: whether a candidate was applied; ``False`` when the completer returned nothing but the current text
            and position.
        :raises ValueError: a candidate is longer than :attr:`max_length`; the text and the cycle are left as they
            were.
        :raises Exception: what :meth:`set_edit_text` raises for the candidate.
            When it raises before changing the text, the cycle is left as it was.
        """
        if self._completion_cycle is not None and (self._edit_text, self._edit_pos) != self._completion_applied:
            self._end_completion()  # changed without set_edit_pos(), by a subclass
        if self._completion_cycle is None:
            completer = typing.cast("Callable[[str, int], Sequence[tuple[str, int]]]", self._text_completer)
            current = self._completion_candidate(self._edit_text, self._edit_pos)  # the text a step back leaves
            results = [
                candidate
                for text, pos in completer(self._edit_text, self._edit_pos)
                if (candidate := self._completion_candidate(text, pos)) != current
            ]
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
            candidates, index = self._completion_cycle
        index = (index + step) % len(candidates)
        self._completion_hold = True
        try:
            self._set_edit_text_and_pos(*candidates[index])
        finally:
            self._completion_hold = False
        # read back: an override or a "postchange" handler may have changed what was applied
        self._completion_cycle = (candidates, index)
        self._completion_applied = (self._edit_text, self._edit_pos)
        self._emit("completion_cycle", self._completion_cycle)
        return True

    def _completion_candidate(self, text: str | bytes, pos: int) -> tuple[str | bytes, int]:
        """Return a completer's replacement as the edit would hold it once applied.

        The text takes the type of the caption, and the position is clipped as :meth:`set_edit_pos` clips it.
        A candidate equal to the current text and cursor is then recognised and left out,
        and a step leaves exactly the candidate the cycle recorded.
        """
        text = self._normalize_to_caption(text)
        return text, _grapheme_boundary(text, min(max(pos, 0), len(text)), forward=False)

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

        The readline delete commands described in :class:`~urwid.CommandMap` and ``'yank'`` go through
        :meth:`set_edit_text`.
        A subclass whose :meth:`set_edit_text` raises for some text has to handle those commands itself
        once an application binds them, or the exception leaves :meth:`keypress`.

        A key that completes steps the completion cycle, and any other key ends it, see :attr:`text_completer`.

        A key that changes the text is one step of the undo history, see :attr:`undo_limit`.
        A subclass that changes the text after this method returns makes a change from elsewhere, which clears the
        history; it makes the change in an override of :meth:`set_edit_text` or :meth:`insert_text` instead.

        >>> from urwid import Edit
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
        :raises Exception: what :meth:`set_edit_text` raises for a completion, see :attr:`text_completer`.
            What it raises for the text of ``'undo'``, ``'redo'`` or ``'yank'``, see :meth:`undo`.
        """
        with self._editing():
            return self.__keypress(size, key)

    def __keypress(self, size: tuple[int], key: str) -> str | None:
        """Handle a key for :meth:`keypress`, inside its editing transaction."""
        if not (complete_step := self._completion_direction(key)):
            self._end_completion()

        pos = self.edit_pos
        if self.valid_char(key):
            self._undo_kind = "insert"
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
            return None if self._step_completion(complete_step) else key

        command = self._command_map[key]
        if command == Command.MENU or (key == "enter" and command == Command.ACTIVATE):
            # a handler that sets the text makes a change from elsewhere, which clears the undo history
            depth, self._edit_depth = self._edit_depth, 0
            try:
                self._emit("cancel" if command == Command.MENU else "submit", self._edit_text)
            finally:
                self._edit_depth = depth
            return key

        if command == Command.UNDO:
            return None if self.undo() else key

        if command == Command.REDO:
            return None if self.redo() else key

        if command == Command.YANK:
            return None if self._yank() else key

        if command in {Command.WORD_LEFT, Command.WORD_RIGHT, Command.LINE_START, Command.LINE_END}:
            if command == Command.LINE_START:
                new_pos = self._line_bounds(pos)[0]
            elif command == Command.LINE_END:
                new_pos = self._line_bounds(pos)[1]
            else:
                new_pos = self._word_boundary(pos, forward=command == Command.WORD_RIGHT)
            if new_pos == pos:
                return key
            self.set_edit_pos(new_pos)
            return None

        if command in {
            Command.DELETE_WORD_LEFT,
            Command.DELETE_WORD_RIGHT,
            Command.DELETE_SPACE_WORD_LEFT,
            Command.DELETE_TO_LINE_START,
            Command.DELETE_TO_LINE_END,
        }:
            text = self._edit_text
            if command == Command.DELETE_WORD_LEFT:
                start, end = self._word_boundary(pos, forward=False), pos
            elif command == Command.DELETE_SPACE_WORD_LEFT:
                start, end = self._word_boundary(pos, forward=False, space_separated=True), pos
            elif command == Command.DELETE_WORD_RIGHT:
                start, end = pos, self._word_boundary(pos, forward=True)
            elif command == Command.DELETE_TO_LINE_START:
                start, end = self._line_bounds(pos)[0], pos
            else:
                start, end = pos, self._line_bounds(pos)[1]
            if start == end:
                return key
            self._set_edit_text_and_pos(text[:start] + text[end:], start)
            self._kill(text[start:end], forward=command in {Command.DELETE_WORD_RIGHT, Command.DELETE_TO_LINE_END})
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
            self._undo_kind = "backspace"
            self.pref_col_maxcol = None, None
            if not self._delete_highlighted():
                if pos == 0:
                    return key
                pos = move_prev_char(self.edit_text, 0, pos)
                self._set_edit_text_and_pos(self.edit_text[:pos] + self.edit_text[self.edit_pos :], pos)
                return None
            return None

        if key == "delete" or command == Command.DELETE_RIGHT:
            self._undo_kind = "delete"
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

    def _line_bounds(self, pos: int) -> tuple[int, int]:
        """Return the start and the end of the line *pos* is on, where a line ends at a newline."""
        text = self._edit_text
        nl = "\n" if isinstance(text, str) else b"\n"
        eol = text.find(nl, pos)  # pyrefly: ignore[bad-argument-type]  # isinstance() does not narrow nl
        bol = text.rfind(nl, 0, pos)  # pyrefly: ignore[bad-argument-type]  # isinstance() does not narrow nl
        return bol + 1, len(text) if eol < 0 else eol

    def _word_boundary(self, pos: int, *, forward: bool, space_separated: bool = False) -> int:
        """Return the edit position after the next word, or at the start of the previous word.

        A word is a run of characters whose first code point is a letter, a digit or an underscore.
        With *space_separated*, a word is a run of characters whose first code point is not whitespace.
        A multibyte character of a byte string counts as a letter.
        A masked text is one word, so that the cursor does not show where the hidden text has spaces.
        """
        text = self._edit_text
        end = len(text)
        if self._mask is not None:
            return end if forward else 0

        def in_word(char: str | bytes) -> bool:
            if space_separated:
                return not char[:1].isspace()
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

    def _delete_highlighted(self) -> bool:
        """Delete all highlighted text and update cursor position, if any text is highlighted."""
        if not self.highlight:
            return False
        start, stop = self.highlight
        btext, etext = self.edit_text[:start], self.edit_text[stop:]
        self._set_edit_text_and_pos(btext + etext, start)
        self.highlight = None
        return True
