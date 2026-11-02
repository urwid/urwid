"""Type checker fixture for the placeholder, validator, completer, undo and kill buffer options of Edit.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, MutableSequence
    from typing import assert_type

    import urwid

    def check_port(text: str) -> urwid.ValidationMessage | str | None:
        """Return one message, an error string or None, as a validator may."""
        return None if text.isdigit() else "not a port number"

    def check_all(text: str) -> list[urwid.ValidationMessage]:
        """Return several messages, as a validator may."""
        return [urwid.ValidationMessage(urwid.Severity.INFO, text)]

    def complete(text: str, pos: int) -> list[tuple[str, int]]:
        """Return whole replacements, as a completer does."""
        return [(text + "x", pos + 1)]

    def edit_options(plain: dict[str, str], kills: list[str | bytes]) -> None:
        """Accept the new options in their documented forms, and type what the properties return."""
        edit = urwid.Edit(
            "Port: ",
            placeholder=("hint", "8080"),
            placeholder_grow=True,
            validator=check_port,
            validation_attr={urwid.Severity.ERROR: "error", urwid.Severity.WARNING: plain},
            validation_focus_attr={urwid.Severity.ERROR: "error focus"},
            text_completer=complete,
            undo_limit=50,
            kill_buffer=kills,
        )
        edit.validator = check_all
        edit.validator = None
        edit.validation_attr = None
        edit.text_completer = None
        assert_type(edit.validation, tuple[urwid.ValidationMessage, ...])
        assert_type(edit.severity, urwid.Severity | None)
        assert_type(edit.validate(), tuple[urwid.ValidationMessage, ...])
        assert_type(edit.validation_attr, dict[urwid.Severity, dict[Hashable, Hashable]])
        assert_type(edit.completion_cycle, tuple[tuple[tuple[str | bytes, int], ...], int] | None)
        assert_type(edit.undo_limit, int)
        assert_type(edit.undo(), bool)
        assert_type(edit.redo(), bool)
        assert_type(edit.kill_buffer, MutableSequence[str | bytes] | None)
        edit.undo_limit = 0
        edit.kill_buffer = None
