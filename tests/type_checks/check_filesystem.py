"""Type checker fixture for PathCompleter, DirectoryReader and FileEntry.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence
    from typing import assert_type

    import urwid
    from urwid.widget import DirectoryReader, FileEntry

    def by_length(entry: FileEntry) -> int:
        """Order entries by the length of their name, as a sort key may."""
        return len(entry.name)

    def completer_is_an_edit_completer(reader: DirectoryReader, base: pathlib.Path) -> None:
        """Pass a completer where Edit takes a text completer, and type what it returns."""
        completer = urwid.PathCompleter(reader, base_dir=base, only_directories=True, sort_key=by_length)
        urwid.Edit("Path: ", text_completer=completer)
        assert_type(completer("a", 1), Sequence[tuple[str, int]])
        assert_type(completer.base_dir, str | None)
        completer.base_dir = base

    def reader_api(reader: DirectoryReader, path: pathlib.Path) -> None:
        """Type what the reader returns."""
        assert_type(reader.read(path), list[FileEntry])
        assert_type(reader.entry(path), FileEntry)
        assert_type(reader.resolve(path), str)
        assert_type(DirectoryReader.name_key("a1"), tuple[str | int, ...])
        DirectoryReader(root_dir=path, show=urwid.FileKind.FILE | urwid.FileKind.DIRECTORY, patterns=["*.py"])
        DirectoryReader(show=lambda entry: not entry.hidden)
