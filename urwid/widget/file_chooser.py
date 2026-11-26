# Copyright (C) 2026 Urwid developers
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/

"""FileChooser: a path field joined to the list of one directory."""

from __future__ import annotations

import os
import pathlib
import time
import typing

from urwid import signals
from urwid.command_map import Command

from .attr_map import AttrMap
from .constants import BOX_SYMBOLS, Align, WHSettings
from .divider import Divider
from .edit import Edit
from .filesystem import _SEPARATORS, DirectoryReader, FileEntry, FileKind, PathCompleter
from .pile import Pile
from .table import Table, TableColumn, TableRow
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Sequence

    from _typeshed import SupportsRichComparison

    from urwid.util import _TagMarkup

    from .attr_map import _AttrMapLike
    from .text import Text
    from .widget import Widget

__all__ = ("FileChooser",)

# row groups, in display order whatever the sort direction
_PARENT, _SHOWN, _STATUS, _DIRECTORY, _FILE = range(5)
_COMPLETION_COMMANDS: typing.Final = frozenset((Command.COMPLETE_NEXT, Command.COMPLETE_PREVIOUS))
_REMEMBERED_LIMIT: typing.Final = 64  # directories whose focused name is kept for coming back to them
_KIBI: typing.Final = 1024
_ONE_DECIMAL_BELOW: typing.Final = 10  # a size in units below this keeps one decimal


def _format_size(size: int) -> str:
    """Return *size* in bytes, or in binary units with one letter from 1024 bytes on.

    >>> _format_size(1000), _format_size(1536), _format_size(20 * 1024**2)
    ('1000', '1.5K', '20M')
    """
    value, unit = float(size), ""
    for larger in "KMGT":
        if value < _KIBI:
            break
        value, unit = value / _KIBI, larger
    if not unit:
        return str(size)
    return f"{value:.1f}{unit}" if value < _ONE_DECIMAL_BELOW else f"{value:.0f}{unit}"


class _ChooserRow(TableRow):
    """A row of the chooser, which knows its group and records a press of button 1 on itself."""

    def __init__(
        self,
        table: Table,
        cells: Sequence[_TagMarkup | Widget],
        *,
        data: FileEntry | None,
        group: int,
        attr: _AttrMapLike | None = None,
        span: bool = False,
    ) -> None:
        """Build the row; a status row (*data* ``None``) takes no focus."""
        super().__init__(table.layout, cells, data=data, attr=attr, selectable=data is not None, span=span)
        self.group = group
        self.pressed = False

    def mouse_event(
        self,
        size: tuple[int],  # type: ignore[override]
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Record a press of button 1, then pass the event on."""
        if event == "mouse press" and button == 1:
            self.pressed = True
        return super().mouse_event(size, event, button, col, row, focus)


class FileChooser(WidgetWrap[Pile]):
    """A path field joined to a sortable :class:`Table` of one directory, for opening or saving files.

    The field and the list follow each other, one direction at a time: moving in the list writes the field,
    and typing in the field focuses the matching row and shows a typed directory, leaving the text as typed.
    Relative text is taken from the directory the chooser last wrote into the field.
    :kbd:`tab` completes the field with :class:`PathCompleter`, and gives the focus to the list when nothing
    completes. :kbd:`enter` on a directory row, or :kbd:`right`, enters it; :kbd:`left` goes to the parent.

    :meth:`accept` (:kbd:`enter` in the field, or an OK button of the dialog) and the activation of a file row
    validate the candidates and send ``"accept"`` with the chooser and a tuple of :class:`pathlib.Path`.
    A handler returning a true value vetoes it, such as one asking whether to overwrite.
    A refused path sends ``"refused"`` with the chooser, the path and the reason.
    A directory is accepted only as the directory shown: through the ``.`` row, or a field that is empty or names it.

    Sends ``"directory changed"`` with the old and the new directory, and with *multiple*
    ``"selection changed"`` with :attr:`selection`.
    *root_dir* limits what is listed, completed and accepted to that directory, judged on resolved paths,
    see :class:`DirectoryReader`.
    """

    signals: typing.ClassVar[list[str]] = ["accept", "refused", "directory changed", "selection changed"]

    def __init__(
        self,
        start_path: str | os.PathLike[str] | None = None,
        *,
        select: FileKind | Callable[[FileEntry], bool] = FileKind.FILE,
        show: FileKind | Callable[[FileEntry], bool] = FileKind.ANY,
        patterns: Iterable[str] = (),
        show_hidden: bool = False,
        must_exist: bool = True,
        root_dir: str | os.PathLike[str] | None = None,
        reader: DirectoryReader | None = None,
        sort_key: Callable[[FileEntry], SupportsRichComparison] | None = None,
        columns: Sequence[typing.Literal["name", "size", "modified"]] = ("name", "size", "modified"),
        max_rows: int | None = None,
        multiple: bool = False,
        mark_keys: Iterable[str] = ("insert", " "),
        caption: _TagMarkup = "",
        divider: str | None = BOX_SYMBOLS.LIGHT.HORIZONTAL,
        attr: _AttrMapLike | None = None,
        focus_attr: _AttrMapLike | None = None,
        unfocused_focus_attr: _AttrMapLike | None = None,
        dim_attr: _AttrMapLike | None = None,
        mark_attr: _AttrMapLike | None = None,
        error_attr: _AttrMapLike | None = None,
        field_attr: _AttrMapLike | None = None,
        field_focus_attr: _AttrMapLike | None = None,
        header_attr: _AttrMapLike | None = None,
        header_focus_attr: _AttrMapLike | None = None,
    ) -> None:
        """Create the chooser and read its first directory.

        :param start_path: a directory to show, a file to focus in its directory, or a missing name to put in the
            field; ``None`` is the root directory when one is given, else the working directory
        :param select: kinds of entries that can be accepted, or a predicate called with each entry
        :param show: kinds of entries listed, or a predicate; see :class:`DirectoryReader`
        :param patterns: :mod:`fnmatch` patterns that names other than directories have to match
        :param show_hidden: list hidden entries; see :attr:`show_hidden`
        :param must_exist: refuse a typed name that does not exist; ``False`` for saving under a new name
        :param root_dir: the directory nothing outside of is listed or accepted
        :param reader: the listing policy, replacing *show*, *patterns*, *show_hidden* and *root_dir*
        :param sort_key: ``sort_key(entry)`` ordering names, for the list and the completion;
            ``None`` uses :meth:`DirectoryReader.name_key`
        :param columns: the columns of the list, in order
        :param max_rows: the most rows a flow size shows; ``None`` shows every row
        :param multiple: allow marking several entries, see :attr:`selection`
        :param mark_keys: the keys that mark the focused row in the list while *multiple* is set
        :param caption: the caption of the path field
        :param divider: the character of the line between the field and the list; ``None`` draws no line
        :param attr: attribute of the rows
        :param focus_attr: attribute of the focused row
        :param unfocused_focus_attr: attribute of the focused row while the field has the focus,
            so the row the field names stays visible
        :param dim_attr: attribute of a file that cannot be accepted, and of an entry outside the root directory
        :param mark_attr: attribute of a marked entry
        :param error_attr: attribute of the status row
        :param field_attr: attribute of the path field
        :param field_focus_attr: attribute of the path field while it has the focus
        :param header_attr: attribute of the column labels
        :param header_focus_attr: attribute of the focused column label
        :raises ValueError: *start_path* is outside the root directory.
            Also when the directory of *start_path* does not resolve, so it cannot be judged against the root.
        """
        self._reader = (
            DirectoryReader(root_dir=root_dir, show=show, patterns=patterns, show_hidden=show_hidden)
            if reader is None
            else reader
        )
        self._select = select
        self._must_exist = must_exist
        self._sort_key = sort_key
        self._multiple = multiple
        self._mark_keys = frozenset(mark_keys)
        self._dim_attr, self._mark_attr, self._error_attr = dim_attr, mark_attr, error_attr
        self._marks: dict[str, FileEntry] = {}
        self._remembered: dict[str, str] = {}
        self._error: OSError | None = None
        self._current_dir = ""
        self._field_base = ""
        self._field_entry: FileEntry | None = None
        self._from_field = self._rebuilding = self._syncing = self._completing = False
        self._sort: tuple[Hashable, bool] = ("name" if "name" in columns else columns[0], False)
        self._columns = tuple(columns)

        specs = [TableColumn("", 1, key="mark")] if multiple else []
        for name in self._columns:
            match name:
                case "name":
                    specs.append(TableColumn("Name", (WHSettings.WEIGHT, 1), key=name))
                case "size":
                    specs.append(TableColumn("Size", WHSettings.PACK, align=Align.RIGHT, key=name))
                case "modified":
                    specs.append(TableColumn("Modified", WHSettings.PACK, key=name))
                case _:
                    typing.assert_never(name)
        self._completer = PathCompleter(self._reader, sort_key=sort_key)
        #: The path field, for a dialog to decorate.
        self.path_edit = Edit(caption, text_completer=self._completer)
        #: The list of the directory shown, for a dialog to decorate.
        self.table = Table(
            specs,
            sortable=True,
            select_navigation=True,
            max_rows=max_rows,
            attr=attr,
            focus_attr=focus_attr,
            unfocused_focus_attr=unfocused_focus_attr,
            header_attr=header_attr,
            header_focus_attr=header_focus_attr,
        )
        if multiple:
            self.table.footer = TableRow(self.table.layout, ["0 selected"], span=True)
        signals.connect_signal(self.path_edit, "postchange", FileChooser._field_changed, weak_args=[self])
        signals.connect_signal(self.table, "focus changed", FileChooser._row_focused, weak_args=[self])
        signals.connect_signal(self.table, "activate", FileChooser._activated, weak_args=[self])
        signals.connect_signal(self.table, "header activated", FileChooser._header_activated, weak_args=[self])
        field = AttrMap(self.path_edit, field_attr, field_focus_attr)
        super().__init__(Pile([(WHSettings.PACK, field), (WHSettings.WEIGHT, 1, self.table)]))
        if divider is not None:
            self._w.contents.insert(1, (Divider(divider), self._w.options(WHSettings.PACK)))
        # the Pile position of the list, after the optional line
        self._list_position = len(self._w.contents) - 1
        self._w.select_navigation = True
        self._start(start_path)

    def _start(self, start_path: str | os.PathLike[str] | None) -> None:
        """Show the directory of *start_path* and fill the field, as :meth:`__init__` describes."""
        if start_path is None:
            start_path = self._reader.root_dir or os.getcwd()
        entry = self._reader.entry(start_path)
        outside = f"{os.fspath(start_path)!r} is outside the root directory {self._reader.root_dir!r}"
        if entry.outside_root:  # judged first, so the message does not tell whether an outside path exists
            raise ValueError(outside)
        shown = entry.exists and entry.kind == FileKind.DIRECTORY and entry.resolved is not None
        if shown:
            directory = typing.cast("str", entry.resolved)
        else:
            parent = os.path.dirname(entry.path.rstrip(_SEPARATORS)) or os.curdir
            try:
                directory = self._reader.resolve(parent)
            except OSError as exc:
                # an unresolved path cannot be judged against the root
                raise ValueError(f"the directory of {os.fspath(start_path)!r} cannot be resolved: {exc}") from exc
        if not self._reader.contains(directory):
            raise ValueError(outside)
        if shown:
            self._show_directory(directory, focus=())
            self._write_field(os.path.join(directory, ""), None)
            return
        self._show_directory(directory, focus=(entry.name,))
        self._write_field(os.path.join(directory, entry.display_name), None)
        if (
            entry.exists
            and (row := self.table.focus) is not None
            and row.data is not None
            and row.data.name == entry.name
        ):
            self._write_row(row)

    # --- properties

    @property
    def reader(self) -> DirectoryReader:
        """The listing policy that the list and the completion share."""
        return self._reader

    @property
    def current_dir(self) -> str:
        """The resolved directory shown."""
        return self._current_dir

    @property
    def error(self) -> OSError | None:
        """The error that kept the directory shown from being listed, or ``None``."""
        return self._error

    @property
    def selection(self) -> tuple[pathlib.Path, ...]:
        """The marked paths, in the order they were marked."""
        return tuple(pathlib.Path(entry.path) for entry in self._marks.values())

    @property
    def show_hidden(self) -> bool:
        """Whether hidden entries are listed; setting it lists the directory again."""
        return self._reader.show_hidden

    @show_hidden.setter
    def show_hidden(self, show_hidden: bool) -> None:
        self._reader.show_hidden = show_hidden
        self.refresh()

    # --- rows

    def make_cells(self, entry: FileEntry) -> list[_TagMarkup | Widget]:
        """Return the cells of the columns for *entry*; override for other cells."""
        cells: list[_TagMarkup | Widget] = []
        for column in self._columns:
            match column:
                case "name":
                    suffix = os.sep if entry.kind == FileKind.DIRECTORY and entry.name not in {".", ".."} else ""
                    link = " -> " + entry.link_target if entry.is_symlink and entry.link_target else ""
                    cells.append(entry.display_name + suffix + link)
                case "size":
                    regular = entry.size is not None and entry.kind != FileKind.DIRECTORY
                    cells.append(_format_size(typing.cast("int", entry.size)) if regular else "")
                case "modified":
                    stamp = entry.mtime
                    cells.append("" if stamp is None else time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp)))
                case _:
                    typing.assert_never(column)
        return cells

    def _row(self, entry: FileEntry, group: int) -> _ChooserRow:
        """Build the row of *entry* in *group*."""
        cells = self.make_cells(entry)
        marked = group in {_DIRECTORY, _FILE} and entry.path in self._marks
        if self._multiple:
            cells.insert(0, "*" if marked else "")
        attr = self._mark_attr if marked else None
        if self._dimmed(entry, group):
            attr = self._dim_attr
        return _ChooserRow(self.table, cells, data=entry, group=group, attr=attr)

    def _dimmed(self, entry: FileEntry, group: int) -> bool:
        """Return whether the row of *entry* in *group* is drawn dimmed.

        An entry outside the root is dimmed, and so is a file that *select* rejects.
        A directory that *select* rejects is not: the list enters it.
        """
        if group not in {_DIRECTORY, _FILE}:
            return False
        return entry.outside_root or (group == _FILE and not self._allows(entry))

    def _show_directory(
        self,
        directory: str,
        *,
        focus: Sequence[str],
        fallback: int = 0,
        entries: list[FileEntry] | None = None,
    ) -> None:
        """Show the resolved *directory* and focus the first row named in *focus*, else the row at *fallback*.

        :param entries: the entries already read, ``None`` to read them
        """
        self._error = None
        if entries is None:
            try:
                entries = self._reader.read(directory)
            except OSError as exc:
                entries = []
                self._error = exc
        old, self._current_dir = self._current_dir, directory
        rows: list[_ChooserRow] = []
        parent = os.path.dirname(directory)
        if directory not in {parent, self._reader.root_dir}:
            rows.append(self._row(FileEntry("..", parent, parent, FileKind.DIRECTORY), _PARENT))
        if self._allows(FileEntry(".", directory, directory, FileKind.DIRECTORY)):
            rows.append(self._row(FileEntry(".", directory, directory, FileKind.DIRECTORY), _SHOWN))
        if self._error is not None or not entries:
            message = "(empty)" if self._error is None else f"({self._error.strerror or self._error})"
            status = _ChooserRow(self.table, [message], data=None, group=_STATUS, attr=self._error_attr, span=True)
            rows.append(status)
        rows.extend(self._row(entry, _DIRECTORY if entry.kind == FileKind.DIRECTORY else _FILE) for entry in entries)
        self._rebuilding = True
        try:
            self.table.body[:] = rows
            self._apply_sort()
            names = [row.data.name if row.data is not None else None for row in self.table.body]
            if (position := next((names.index(name) for name in focus if name in names), None)) is None:
                position = min(max(fallback, 0), len(names) - 1)
            self._focus_row(position)
        finally:
            self._rebuilding = False
        if old and old != directory:
            self._emit("directory changed", old, directory)

    def _focus_row(self, position: int) -> None:
        """Focus the row at *position*, or the next selectable row after it."""
        body = self.table.body
        for index in (*range(position, len(body)), *range(position - 1, -1, -1)):
            if body[index].selectable():
                self.table.focus_position = index
                return

    def _row_key(self, column: Hashable, reverse: bool) -> Callable[[TableRow], SupportsRichComparison]:
        """Return the sort key of *column*, keeping the groups in order whatever *reverse* is."""
        name_key = self._sort_key or (lambda entry: self._reader.name_key(entry.name))

        def key(row: TableRow) -> SupportsRichComparison:
            group = typing.cast("_ChooserRow", row).group
            entry: FileEntry | None = row.data
            if entry is None:
                value: typing.Any = 0
            elif column == "size":
                value = entry.size or 0
            elif column == "modified":
                value = entry.mtime or 0.0
            else:
                value = (name_key(entry), entry.name)
            return (-group if reverse else group, value)

        return key

    def _apply_sort(self) -> None:
        """Sort the rows by the column and direction last chosen."""
        column, reverse = self._sort
        self.table.sort(column, key=self._row_key(column, reverse), reverse=reverse)

    def refresh(self) -> None:
        """List the directory shown again, keeping the field as it is."""
        names = []
        if self._field_entry is not None:
            names.append(self._field_entry.name)
        else:
            text = self.path_edit.edit_text
            names.append(os.path.basename(text))
        if (row := self.table.focus) is not None and row.data is not None:
            names.append(row.data.name)
        fallback = self.table.focus_position if self.table.body else 0
        self._from_field = True
        try:
            self._show_directory(self._current_dir, focus=names, fallback=fallback)
        finally:
            self._from_field = False

    # --- the field

    def _write_field(self, text: str, entry: FileEntry | None) -> None:
        """Write *text* into the field as the chooser, standing for *entry* when given."""
        self._syncing = True
        try:
            self.path_edit.set_edit_text(text, edit_pos=len(text))
        finally:
            self._syncing = False
        self._field_entry = entry
        self._field_base = self._current_dir
        self._completer.base_dir = self._current_dir

    def _write_row(self, row: TableRow) -> None:
        """Write the path of *row* into the field."""
        entry: FileEntry | None = row.data
        if entry is None or typing.cast("_ChooserRow", row).group in {_PARENT, _SHOWN}:
            self._write_field(os.path.join(self._current_dir, ""), None)
        else:
            self._write_field(os.path.join(self._current_dir, entry.display_name), entry)

    def _typed_path(self, text: str) -> str:
        """Return the path the typed *text* stands for, joined to the field's base directory."""
        if self._completer.expanduser and text.startswith("~"):
            text = os.path.expanduser(text)
        return os.path.join(self._field_base, text)

    def _focus_name(self, name: str, *, exact: bool = False) -> None:
        """Focus the row named *name*, else, unless *exact*, the first row whose name starts with it."""
        folded = os.path.normcase(name)
        rows = [
            (index, os.path.normcase(row.data.name))
            for index, row in enumerate(self.table.body)
            if row.data is not None and typing.cast("_ChooserRow", row).group in {_DIRECTORY, _FILE}
        ]
        for index, row_name in rows:
            if row_name == folded:
                self.table.focus_position = index
                return
        for index, row_name in rows:
            if not exact and row_name.startswith(folded):
                self.table.focus_position = index
                return

    def _field_changed(self, _edit: Edit, _old: str) -> None:
        """Follow a change of the field that the chooser did not make, as the class describes."""
        if self._syncing:
            return
        self._field_entry = None
        text = self.path_edit.edit_text
        directory, name = os.path.split(self._typed_path(text))
        try:
            resolved = self._reader.resolve(directory)
        except OSError:
            return
        self._from_field = True
        try:
            if resolved == self._current_dir:
                self._focus_name(name, exact=self._completing)
            elif not self._completing and self._reader.contains(resolved):
                try:
                    entries = self._reader.read(resolved)
                except OSError:
                    return
                self._remember()
                self._show_directory(resolved, focus=(), entries=entries)
                self._focus_name(name)
        finally:
            self._from_field = False

    def _row_focused(self, _table: Table, _old: int | None, _new: int | None) -> None:
        """Write the field for a focus move in the list."""
        if not (self._from_field or self._rebuilding) and (row := self.table.focus) is not None:
            self._write_row(row)

    # --- navigation

    def _remember(self) -> None:
        """Remember the focused name of the directory shown."""
        if (row := self.table.focus) is not None and row.data is not None:
            self._remembered.pop(self._current_dir, None)
            self._remembered[self._current_dir] = row.data.name
            while len(self._remembered) > _REMEMBERED_LIMIT:
                del self._remembered[next(iter(self._remembered))]

    def _enter(self, directory: str) -> None:
        """Show the resolved *directory* from the list, and write the field from the focused row."""
        left = self._current_dir
        self._remember()
        fallback = self.table.focus_position if self.table.body else 0
        remembered = self._remembered.get(directory)
        if os.path.dirname(left) == directory:
            focus = [os.path.basename(left)] + ([remembered] if remembered else [])
            self._show_directory(directory, focus=focus, fallback=fallback)
        else:
            self._show_directory(directory, focus=[remembered] if remembered else [])
        if (row := self.table.focus) is not None:
            self._write_row(row)

    def _enter_parent(self) -> bool:
        """Enter the parent directory when the list has a ``..`` row."""
        row = self.table.body[0] if self.table.body else None
        if row is None or typing.cast("_ChooserRow", row).group != _PARENT:
            return False
        self._enter(os.path.dirname(self._current_dir))
        return True

    def _enterable(self, entry: FileEntry | None) -> bool:
        """Return whether *entry* is a directory row the list enters."""
        return entry is not None and entry.kind == FileKind.DIRECTORY and not entry.outside_root

    def _activated(self, _table: Table, _position: int) -> bool:
        """Activate the focused row, as :meth:`accept` describes for rows."""
        row = typing.cast("_ChooserRow | None", self.table.focus)
        if row is None or row.data is None:
            return True
        if row.group == _PARENT:
            self._enter_parent()
        elif row.group == _SHOWN:
            self._accept_paths([entry.path for entry in self._marks.values()] or [self._current_dir])
        elif self._enterable(row.data) and row.data.resolved is not None:
            self._enter(row.data.resolved)
        else:
            self._accept_paths([entry.path for entry in self._marks.values()] or [row.data.path])
        return True

    def _header_activated(self, _table: Table, column: int) -> bool:
        """Sort by *column*, turning the direction round when it is the column already sorted by."""
        if (key := self.table.layout.columns[column].key) == "mark":
            return False
        reverse = self._sort[0] == key and not self._sort[1]
        self._sort = (key, reverse)
        self._apply_sort()
        return True

    # --- accepting

    def _allows(self, entry: FileEntry) -> bool:
        """Return whether *select* allows *entry*."""
        return entry.kind in self._select if isinstance(self._select, FileKind) else self._select(entry)

    def _refusal(self, path: str, *, typed: bool) -> str | None:
        """Return why *path* cannot be accepted, or ``None`` when it can."""
        entry = self._reader.entry(path)
        if entry.outside_root:
            return "outside the root directory"
        if entry.error is not None:
            return f"cannot be read: {entry.error.strerror or entry.error}"
        if entry.exists:
            if not self._allows(entry):
                return "is a directory" if entry.kind == FileKind.DIRECTORY else "cannot be selected"
            if entry.kind != FileKind.DIRECTORY and not self._reader.name_matches(entry.name):
                return "does not match the patterns"
            return None
        if not typed or self._must_exist:
            return "does not exist"
        if (name := os.path.basename(path)) in {"", os.curdir, os.pardir}:
            return "is not a file name"
        parent = self._reader.entry(os.path.dirname(path) or os.curdir)
        if not parent.exists or parent.error is not None or parent.kind != FileKind.DIRECTORY:
            return "the parent directory does not exist"
        new = FileEntry(name, path, entry.resolved, FileKind.FILE, exists=False)
        if not self._allows(new) or not self._reader.name_matches(name):
            return "cannot be selected"
        return None

    def _accept_paths(self, paths: Sequence[str], *, typed: bool = False) -> bool:
        """Validate every path, then send ``"accept"``; return whether they were accepted."""
        for path in paths:
            if (reason := self._refusal(path, typed=typed)) is not None:
                self._emit("refused", path, reason)
                return False
        return not signals.emit_signal(self, "accept", self, tuple(pathlib.Path(path) for path in paths))

    def accept(self) -> bool:
        """Accept the path in the field, the marks, or the directory shown, as the class describes.

        A field naming another directory enters it instead.

        :returns: whether paths were accepted; ``False`` when refused, vetoed, or a directory was entered.
        """
        text = self.path_edit.edit_text
        path = self._typed_path(text) if self._field_entry is None else self._field_entry.path
        entry = self._reader.entry(path) if text else None
        if (
            entry is not None
            and entry.kind == FileKind.DIRECTORY
            and not entry.outside_root
            and entry.resolved is not None
            and entry.resolved != self._current_dir
        ):
            self._enter(entry.resolved)
            return False
        if self._marks:
            return self._accept_paths([marked.path for marked in self._marks.values()])
        if entry is None or entry.resolved == self._current_dir:
            return self._accept_paths([self._current_dir])
        return self._accept_paths([path], typed=self._field_entry is None)

    # --- marks

    def _set_marks(self, marks: dict[str, FileEntry]) -> None:
        """Replace the marks, update the rows and the footer, and send ``"selection changed"``."""
        self._marks = marks
        for row in self.table.body:
            if (entry := row.data) is not None and typing.cast("_ChooserRow", row).group in {_DIRECTORY, _FILE}:
                marked = entry.path in marks
                typing.cast("Text", row.cells[0]).set_text("*" if marked else "")
                if not self._dimmed(entry, _DIRECTORY if entry.kind == FileKind.DIRECTORY else _FILE):
                    row.attr = self._mark_attr if marked else None
        if (footer := self.table.footer) is not None:
            typing.cast("Text", footer.cells[0]).set_text(f"{len(marks)} selected")
        self._emit("selection changed", self.selection)

    def toggle_mark(self) -> bool:
        """Mark or unmark the focused row when it can be accepted; return whether it changed."""
        row = typing.cast("_ChooserRow | None", self.table.focus)
        if not self._multiple or row is None or row.data is None or row.group not in {_DIRECTORY, _FILE}:
            return False
        marks = self._marks.copy()
        if marks.pop(row.data.path, None) is None:
            if self._refusal(row.data.path, typed=False) is not None:
                return False
            marks[row.data.path] = row.data
        self._set_marks(marks)
        return True

    def select_all(self) -> None:
        """Mark every entry of the directory shown that can be accepted; nothing without *multiple*."""
        if not self._multiple:
            return
        marks = self._marks.copy()
        for row in self.table.body:
            entry = row.data
            if (
                entry is not None
                and typing.cast("_ChooserRow", row).group in {_DIRECTORY, _FILE}
                and entry.path not in marks
                and self._refusal(entry.path, typed=False) is None
            ):
                marks[entry.path] = entry
        self._set_marks(marks)

    def clear_selection(self) -> None:
        """Remove every mark; nothing without *multiple*."""
        if not self._multiple:
            return
        self._set_marks({})

    # --- input

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Route *key* between the field and the list, as the class describes."""
        command = self._command_map[key]
        if self._w.focus_position == 0:
            completing = key in {"tab", "shift tab"} or command in _COMPLETION_COMMANDS
            self._completing = completing
            try:
                unhandled = self.path_edit.keypress((size[0],) if size else (0,), key)
            finally:
                self._completing = False
            if unhandled is None:
                return None
            if key == "enter":
                self.accept()
                return None
            if (key == "tab" or command == Command.DOWN) and any(row.selectable() for row in self.table.body):
                self._w.focus_position = self._list_position
                return None
            return unhandled
        if self._multiple and key in self._mark_keys and self.table.header_column is None:
            self.toggle_mark()
            return None
        if key in {"backspace", "delete"} or self.path_edit.valid_char(key):
            self.table.header_column = None
            self._w.focus_position = 0
            return self.path_edit.keypress((size[0],) if size else (0,), key)
        unhandled = super().keypress(size, key)
        if unhandled is not None and self.table.header_column is None and self._w.focus_position == self._list_position:
            if command == Command.LEFT and self._enter_parent():
                return None
            row = self.table.focus
            if (
                command == Command.RIGHT
                and row is not None
                and typing.cast("_ChooserRow", row).group == _DIRECTORY
                and self._enterable(row.data)
            ):
                self._enter(typing.cast("str", row.data.resolved))
                return None
        return unhandled

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Pass the event on; a second press of button 1 on the focused row activates it."""
        rows_focused = self._w.focus_position == self._list_position and self.table.header_column is None
        before = typing.cast("_ChooserRow | None", self.table.focus) if rows_focused else None
        if before is not None:
            before.pressed = False
        handled = super().mouse_event(size, event, button, col, row, focus)
        if before is not None and before.pressed and self.table.focus is before:
            before.pressed = False
            self._activated(self.table, self.table.focus_position)
            return True
        return handled

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Focus the field, or with *reverse* the list when it has a row to focus, keeping the row focus."""
        has_rows = any(row.selectable() for row in self.table.body)
        if has_rows:
            self.table.header_column = None
        self._w.focus_position = self._list_position if reverse and has_rows else 0
