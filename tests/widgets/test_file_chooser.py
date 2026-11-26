"""Tests of FileChooser on a temporary tree."""

from __future__ import annotations

import errno
import gc
import os
import pathlib
import shutil
import sys
import tempfile
import typing
import unittest
import weakref
from unittest import mock

import urwid
import urwid.testing
from urwid.testing import check_sizing, click, press, render_text
from urwid.widget import DirectoryReader, FileEntry

SEP = os.sep
SIZE = (60, 12)
HAS_SYMLINKS = hasattr(os, "symlink") and sys.platform != "win32"
FileKind = urwid.FileKind


class ChooserTestCase(unittest.TestCase):
    """A temporary tree and a chooser on it, with the accepted and refused paths recorded."""

    def setUp(self) -> None:
        """Create the tree root and the signal records."""
        self.root = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        self.accepted: list[tuple[pathlib.Path, ...]] = []
        self.refused: list[tuple[str, str]] = []
        self.veto = False

    def make(self, *names: str) -> None:
        """Create each name: a directory when it ends with ``/``, else an empty file."""
        for name in names:
            path = self.root / name
            if name.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

    def path(self, *parts: str) -> str:
        """Return the path of *parts* under the root."""
        return str(self.root.joinpath(*parts))

    def chooser(self, start: str | None = None, **kwargs: typing.Any) -> urwid.FileChooser:
        """Create a chooser recording its signals; *start* is relative to the root."""
        kwargs.setdefault("root_dir", self.root)
        chooser = urwid.FileChooser(self.root if start is None else self.root / start, **kwargs)
        urwid.connect_signal(chooser, "accept", self.on_accept)
        urwid.connect_signal(chooser, "refused", self.on_refused)
        return chooser

    def on_accept(self, _chooser: urwid.FileChooser, paths: tuple[pathlib.Path, ...]) -> bool:
        """Record *paths*, and veto them when :attr:`veto` is set."""
        self.accepted.append(paths)
        return self.veto

    def on_refused(self, _chooser: urwid.FileChooser, path: str, reason: str) -> None:
        """Record a refusal."""
        self.refused.append((path, reason))

    @staticmethod
    def names(chooser: urwid.FileChooser) -> list[str | None]:
        """Return the entry name of each row, ``None`` for a status row."""
        return [None if row.data is None else row.data.name for row in chooser.table.body]

    @staticmethod
    def focused(chooser: urwid.FileChooser) -> str | None:
        """Return the entry name of the focused row."""
        row = chooser.table.focus
        return None if row is None or row.data is None else row.data.name

    @staticmethod
    def field(chooser: urwid.FileChooser) -> tuple[str, int]:
        """Return the field text and cursor."""
        return chooser.path_edit.edit_text, chooser.path_edit.edit_pos

    @staticmethod
    def type_text(chooser: urwid.FileChooser, text: str) -> list[str]:
        """Clear the field as the application would, then type *text*."""
        chooser.path_edit.set_edit_text("")
        chooser._w.focus_position = 0
        return press(chooser, SIZE, *text)

    def focus_list(self, chooser: urwid.FileChooser, name: str) -> None:
        """Give the list the focus and move it to the row *name* with the keyboard."""
        chooser._w.focus_position = 1
        names = self.names(chooser)
        self.assertIn(name, names)
        while self.focused(chooser) != name:
            current = names.index(self.focused(chooser))
            press(chooser, SIZE, "down" if names.index(name) > current else "up")


class TestLayout(ChooserTestCase):
    def test_rows_and_groups(self) -> None:
        self.make("b.txt", "a.txt", "dir/", "zdir/")
        chooser = self.chooser("dir")
        self.assertEqual(["..", None], self.names(chooser))
        chooser = self.chooser()
        self.assertEqual(["dir", "zdir", "a.txt", "b.txt"], self.names(chooser))
        self.assertEqual(os.path.join(self.path(""), ""), self.field(chooser)[0])
        lines = render_text(chooser, SIZE, strip=True)
        self.assertIn("dir" + SEP, lines[2])
        self.assertTrue(lines[1].startswith("Name ^"))

    def test_dimmed_rows(self) -> None:
        # the directory is rejected by select as well, but it is entered, so it is not dimmed
        self.make("dir/", "a.txt", "b.py")
        chooser = self.chooser(
            select=lambda entry: entry.kind == FileKind.FILE and entry.name != "a.txt", dim_attr="dim"
        )
        attrs = {row.data.name: row.attr for row in chooser.table.body}
        self.assertEqual({"dir": None, "a.txt": {None: "dim"}, "b.py": None}, attrs)

    def test_row_named_by_field_is_marked_while_field_has_focus(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser("b.txt", unfocused_focus_attr="marked")
        self.assertIs(chooser.path_edit, chooser._w.focus)
        self.assertIn("marked", urwid.testing.attrs_for_text(chooser, SIZE, "b.txt", focus=True))

    def test_directory_mode_has_dot_row(self) -> None:
        self.make("dir/")
        chooser = self.chooser(select=FileKind.DIRECTORY)
        self.assertEqual([".", "dir"], self.names(chooser))

    def test_start_on_file_focuses_it(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser("b.txt")
        self.assertEqual("b.txt", self.focused(chooser))
        self.assertEqual(self.path("b.txt"), self.field(chooser)[0])

    def test_start_on_missing_name(self) -> None:
        self.make("a.txt")
        chooser = self.chooser("new.txt", must_exist=False)
        self.assertEqual(self.path("new.txt"), self.field(chooser)[0])
        self.assertTrue(chooser.accept())
        self.assertEqual([(pathlib.Path(self.path("new.txt")),)], self.accepted)

    def test_start_outside_root(self) -> None:
        self.make("inside/", "outside/")
        with self.assertRaises(ValueError):
            urwid.FileChooser(self.root / "outside", root_dir=self.root / "inside")

    def test_unreadable_start_shows_error_row(self) -> None:
        self.make("dir/")
        with mock.patch.object(DirectoryReader, "scan", side_effect=PermissionError(errno.EACCES, "Permission denied")):
            chooser = self.chooser("dir")
        self.assertIsInstance(chooser.error, PermissionError)
        self.assertIn("(Permission denied)", "\n".join(render_text(chooser, SIZE)))

    def test_sizing(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser(max_rows=3)
        check_sizing(chooser, cols=40, rows=8)

    def test_sort_both_directions_keeps_groups(self) -> None:
        self.make("sub/a/", "sub/b/", "sub/x.txt", "sub/y.txt")
        chooser = self.chooser("sub")
        chooser.table._emit("header activated", 0)
        self.assertEqual(["..", "b", "a", "y.txt", "x.txt"], self.names(chooser))
        self.assertTrue(chooser.table.sort_reverse)
        chooser.table._emit("header activated", 0)
        self.assertEqual(["..", "a", "b", "x.txt", "y.txt"], self.names(chooser))

    def test_columns_without_name(self) -> None:
        self.make("sub/")
        (self.root / "sub" / "big").write_bytes(b"x" * 10)
        (self.root / "sub" / "small").write_bytes(b"x")
        chooser = self.chooser("sub", columns=("size", "modified"))
        self.assertEqual(["..", "small", "big"], self.names(chooser))

    def test_outside_start_says_outside_whether_it_exists_or_not(self) -> None:
        self.make("inside/", "outside/exists/")
        for start in ("outside/exists/x.txt", "outside/missing/x.txt"):
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "outside the root directory"):
                urwid.FileChooser(self.root / start, root_dir=self.root / "inside")

    def test_nul_in_the_field_is_refused(self) -> None:
        self.make("a.txt")
        chooser = self.chooser(must_exist=False)
        chooser.path_edit.set_edit_text("a\0b")
        self.assertFalse(chooser.accept())
        self.assertTrue(self.refused[-1][1].startswith("cannot be read"))

    def test_unresolvable_start_directory_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.chooser(os.path.join("missing", "deeper", "f.txt"))

    def test_sort_by_size(self) -> None:
        self.make("sub/")
        (self.root / "sub" / "big").write_bytes(b"x" * 10)
        (self.root / "sub" / "small").write_bytes(b"x")
        chooser = self.chooser("sub")
        chooser.table._emit("header activated", 1)
        self.assertEqual(["..", "small", "big"], self.names(chooser))
        chooser.table._emit("header activated", 1)
        self.assertEqual(["..", "big", "small"], self.names(chooser))


class TestFieldAndList(ChooserTestCase):
    def test_typing_focuses_matching_row_and_keeps_text(self) -> None:
        self.make("readme.md", "report.txt", "zeta.txt")
        chooser = self.chooser()
        self.type_text(chooser, "rep")
        self.assertEqual("report.txt", self.focused(chooser))
        self.assertEqual(("rep", 3), self.field(chooser))

    def test_moving_in_list_writes_field(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        self.focus_list(chooser, "b.txt")
        self.assertEqual(self.path("b.txt"), self.field(chooser)[0])

    def test_completion_candidate_survives_focus_move(self) -> None:
        self.make("report-1.txt", "report-2.txt")
        chooser = self.chooser()
        self.type_text(chooser, "report-")
        press(chooser, SIZE, "tab")
        self.assertEqual(("report-1.txt", 12), self.field(chooser))
        self.assertEqual("report-1.txt", self.focused(chooser))
        press(chooser, SIZE, "tab")
        self.assertEqual("report-2.txt", self.field(chooser)[0])
        self.assertEqual("report-2.txt", self.focused(chooser))

    def test_completion_moves_focus_on_exact_match_only(self) -> None:
        self.make("a.txt", "rep1.txt", "rep2.log")
        chooser = self.chooser()
        self.type_text(chooser, "a")
        self.assertEqual("a.txt", self.focused(chooser))
        chooser.path_edit.set_edit_text("r")
        chooser._from_field = True  # put the focus back on a.txt without writing the field
        chooser.table.focus_position = 0
        chooser._from_field = False
        press(chooser, SIZE, "tab")
        self.assertEqual("rep", self.field(chooser)[0])
        self.assertEqual("a.txt", self.focused(chooser))
        press(chooser, SIZE, "tab")
        self.assertEqual(("rep1.txt", "rep1.txt"), (self.field(chooser)[0], self.focused(chooser)))

    def test_completion_does_not_change_directory(self) -> None:
        self.make("sub/file.txt", "other.txt")
        chooser = self.chooser()
        self.type_text(chooser, "su")
        press(chooser, SIZE, "tab")
        self.assertEqual("sub" + SEP, self.field(chooser)[0])
        self.assertEqual(self.path(""), chooser.current_dir)

    def test_refresh_and_hidden_toggle_keep_field(self) -> None:
        self.make("a.txt", "b.txt", ".hidden")
        chooser = self.chooser()
        self.type_text(chooser, "b")
        chooser.path_edit.set_edit_pos(0)
        before = self.field(chooser)
        chooser.refresh()
        self.assertEqual(before, self.field(chooser))
        chooser.show_hidden = True
        self.assertIn(".hidden", self.names(chooser))
        self.assertEqual(before, self.field(chooser))
        self.assertEqual("b.txt", self.focused(chooser))

    def test_going_up_focuses_directory_left(self) -> None:
        self.make("a/", "b/x.txt", "c/")
        chooser = self.chooser()
        self.focus_list(chooser, "b")
        press(chooser, SIZE, "enter")
        self.assertEqual(self.path("b"), chooser.current_dir)
        self.assertEqual(self.path("b") + SEP, self.field(chooser)[0])
        press(chooser, SIZE, "left")
        self.assertEqual(self.path(""), chooser.current_dir)
        self.assertEqual("b", self.focused(chooser))
        press(chooser, SIZE, "right")
        self.assertEqual(self.path("b"), chooser.current_dir)

    def test_entering_remembers_focused_name(self) -> None:
        self.make("b/x.txt", "b/y.txt")
        chooser = self.chooser("b")
        self.focus_list(chooser, "y.txt")
        press(chooser, SIZE, "left", "right")
        self.assertEqual("y.txt", self.focused(chooser))

    def test_relative_input_typed(self) -> None:
        self.make("sub/")
        for key in ("ok", "enter"):
            with self.subTest(key=key):
                self.accepted.clear()
                chooser = self.chooser(must_exist=False)
                self.type_text(chooser, "sub" + SEP)
                self.assertEqual(self.path("sub"), chooser.current_dir)
                press(chooser, SIZE, *"file")
                if key == "ok":
                    self.assertTrue(chooser.accept())
                else:
                    self.assertEqual([], press(chooser, SIZE, "enter"))
                self.assertEqual([(pathlib.Path(self.path("sub", "file")),)], self.accepted)

    def test_relative_input_completed(self) -> None:
        self.make("sub/", "other/")
        chooser = self.chooser(must_exist=False)
        self.type_text(chooser, "su")
        press(chooser, SIZE, "tab", *"file")
        self.assertEqual(self.path("sub"), chooser.current_dir)
        self.assertEqual("sub" + SEP + "file", self.field(chooser)[0])
        self.assertTrue(chooser.accept())
        self.assertEqual([(pathlib.Path(self.path("sub", "file")),)], self.accepted)

    def test_non_editable_name_round_trip(self) -> None:
        self.make("tab\tname.txt", "other.txt")
        chooser = self.chooser()
        self.focus_list(chooser, "tab\tname.txt")
        self.assertEqual(self.path("tab�name.txt"), self.field(chooser)[0])
        self.assertTrue(chooser.accept())
        self.assertEqual([(pathlib.Path(self.path("tab\tname.txt")),)], self.accepted)


class TestKeys(ChooserTestCase):
    def test_enter_in_field_handled_once(self) -> None:
        self.make("a.txt")
        chooser = self.chooser("a.txt")
        parent = urwid.Pile([chooser, urwid.Edit()])
        self.assertEqual([], press(parent, (60, 14), "enter"))
        self.assertEqual(1, len(self.accepted))
        self.assertEqual(0, parent.focus_position)

    def test_escape_and_shift_tab_returned(self) -> None:
        self.make("a.txt")
        chooser = self.chooser()
        self.type_text(chooser, "zz")
        self.assertEqual(["esc", "shift tab"], press(chooser, SIZE, "esc", "shift tab"))

    def test_printable_key_in_list_goes_to_field(self) -> None:
        self.make("a.txt")
        chooser = self.chooser()
        start = self.field(chooser)[0]
        cases = (
            ("x", start + "x", []),
            ("backspace", start, []),
            (" ", start + " ", []),
            ("delete", start + " ", ["delete"]),  # nothing after the cursor: the field returns the key
        )
        for key, expected, unhandled in cases:
            with self.subTest(key=key):
                chooser._w.focus_position = 1
                self.assertEqual(unhandled, press(chooser, SIZE, key))
                self.assertIs(chooser.path_edit, chooser._w.focus)
                self.assertEqual(expected, self.field(chooser)[0])

    def test_printable_key_on_header_goes_to_field(self) -> None:
        self.make("a.txt")
        chooser = self.chooser()
        chooser._w.focus_position = 1
        press(chooser, SIZE, "up")
        self.assertIsNotNone(chooser.table.header_column)
        self.assertEqual([], press(chooser, SIZE, "x"))
        self.assertIs(chooser.path_edit, chooser._w.focus)
        self.assertIsNone(chooser.table.header_column)
        self.assertTrue(self.field(chooser)[0].endswith("x"))

    def test_right_on_dot_row_does_nothing(self) -> None:
        self.make("sub/")
        chooser = self.chooser("sub", select=FileKind.DIRECTORY)
        changes: list[str] = []
        urwid.connect_signal(chooser, "directory changed", lambda _chooser, _old, new: changes.append(new))
        self.focus_list(chooser, ".")
        self.assertEqual(["right"], press(chooser, SIZE, "right"))
        self.assertEqual([], changes)

    def test_left_right_on_header_change_no_directory(self) -> None:
        self.make("sub/a.txt")
        chooser = self.chooser("sub")
        chooser._w.focus_position = 1
        press(chooser, SIZE, "up")
        self.assertEqual(0, chooser.table.header_column)
        self.assertEqual(["left"], press(chooser, SIZE, "left"))
        press(chooser, SIZE, "right", "right")
        self.assertEqual(2, chooser.table.header_column)
        self.assertEqual(["right"], press(chooser, SIZE, "right"))
        self.assertEqual(self.path("sub"), chooser.current_dir)

    def test_click_twice_activates_header_click_does_not(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        chooser._w.focus_position = 1
        click(chooser, SIZE, 2, 3)
        self.assertEqual("b.txt", self.focused(chooser))
        self.assertEqual([], self.accepted)
        click(chooser, SIZE, 2, 3)
        self.assertEqual([(pathlib.Path(self.path("b.txt")),)], self.accepted)
        click(chooser, SIZE, 2, 1)
        self.assertEqual(1, len(self.accepted))

    def test_click_with_header_focused_does_not_activate(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        self.focus_list(chooser, "a.txt")
        press(chooser, SIZE, "up")
        self.assertIsNotNone(chooser.table.header_column)
        click(chooser, SIZE, 2, 2)
        self.assertEqual([], self.accepted)
        self.assertIsNone(chooser.table.header_column)

    def test_tab_handoff_keeps_matched_row(self) -> None:
        self.make("alpha.txt", "beta.txt", "gamma.txt")
        for typed in ("beta.txt", "be"):
            with self.subTest(typed=typed):
                self.accepted.clear()
                chooser = self.chooser()
                self.type_text(chooser, typed)
                if typed == "be":
                    press(chooser, SIZE, "tab")  # completes to beta.txt
                self.assertEqual([], press(chooser, SIZE, "tab"))
                self.assertIs(chooser.table, chooser._w.focus)
                self.assertEqual("beta.txt", self.focused(chooser))
                self.assertEqual("beta.txt", self.field(chooser)[0])
                press(chooser, SIZE, "enter")
                self.assertEqual([(pathlib.Path(self.path("beta.txt")),)], self.accepted)

    def test_down_hands_over_to_list(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        self.type_text(chooser, "b")
        self.assertEqual([], press(chooser, SIZE, "down"))
        self.assertIs(chooser.table, chooser._w.focus)
        self.assertEqual("b.txt", self.focused(chooser))

    def test_entry_from_outside_keeps_rows_and_field(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        self.focus_list(chooser, "b.txt")
        before = self.field(chooser)
        parent = urwid.Pile([urwid.Edit(), chooser, urwid.Edit()], focus_item=2)
        parent.select_navigation = True
        press(parent, (60, 16), "shift tab")
        self.assertIs(chooser.table, chooser._w.focus)
        self.assertEqual("b.txt", self.focused(chooser))
        self.assertEqual(before, self.field(chooser))
        parent.focus_position = 0
        press(parent, (60, 16), "tab")
        self.assertIs(chooser.path_edit, chooser._w.focus)
        self.assertEqual("b.txt", self.focused(chooser))
        self.assertEqual(before, self.field(chooser))

    def test_status_only_list_keeps_focus_on_field(self) -> None:
        self.make("empty/")
        errors = (None, PermissionError(errno.EACCES, "Permission denied"))
        for error in errors:
            with self.subTest(error=error):
                patcher = mock.patch.object(DirectoryReader, "scan", side_effect=error) if error else mock.MagicMock()
                with patcher:
                    chooser = urwid.FileChooser(self.root / "empty", root_dir=self.root / "empty")
                self.assertEqual([None], self.names(chooser))
                self.assertEqual(["tab", "down"], press(chooser, SIZE, "tab", "down"))
                self.assertIs(chooser.path_edit, chooser._w.focus)
                chooser.enter_selectable(reverse=True)
                self.assertIs(chooser.path_edit, chooser._w.focus)


class TestAccept(ChooserTestCase):
    def test_row_activation(self) -> None:
        self.make("sub/x.txt", "a.txt")
        chooser = self.chooser()
        self.focus_list(chooser, "sub")
        press(chooser, SIZE, "enter")
        self.assertEqual(self.path("sub"), chooser.current_dir)
        self.assertEqual([], self.accepted)
        self.focus_list(chooser, "..")
        press(chooser, SIZE, "enter")
        self.assertEqual(self.path(""), chooser.current_dir)
        self.focus_list(chooser, "a.txt")
        press(chooser, SIZE, "enter")
        self.assertEqual([(pathlib.Path(self.path("a.txt")),)], self.accepted)

    def test_status_row_does_nothing(self) -> None:
        self.make("empty/")
        chooser = urwid.FileChooser(self.root / "empty", root_dir=self.root / "empty")
        self.assertTrue(chooser._activated(chooser.table, 0))
        self.assertEqual(self.path("empty"), chooser.current_dir)

    def test_dot_row_accepts_directory_shown(self) -> None:
        self.make("dir/")
        chooser = self.chooser(select=FileKind.DIRECTORY)
        self.focus_list(chooser, ".")
        press(chooser, SIZE, "enter")
        self.assertEqual([(pathlib.Path(self.path("")),)], self.accepted)

    def test_field_naming_other_directory_enters_it(self) -> None:
        self.make("sub/")
        for select in (FileKind.FILE, FileKind.DIRECTORY):
            with self.subTest(select=select):
                chooser = self.chooser(select=select)
                chooser.path_edit.set_edit_text(self.path("sub"))
                self.assertEqual(self.path(""), chooser.current_dir)
                self.assertFalse(chooser.accept())
                self.assertEqual(self.path("sub"), chooser.current_dir)
                self.assertEqual([], self.accepted)

    def test_field_naming_shown_directory(self) -> None:
        self.make("a.txt")
        directories = self.chooser(select=FileKind.DIRECTORY)
        self.assertTrue(directories.accept())
        self.assertEqual([(pathlib.Path(self.path("")),)], self.accepted)
        files = self.chooser()
        self.assertFalse(files.accept())
        self.assertEqual("is a directory", self.refused[-1][1])
        files.path_edit.set_edit_text("")
        self.assertFalse(files.accept())

    def test_validation_branches(self) -> None:
        self.make("inside/a.txt", "inside/b.py", "inside/dir/", "outside.txt")
        chooser = urwid.FileChooser(self.root / "inside", root_dir=self.root / "inside", patterns=("*.txt",))
        urwid.connect_signal(chooser, "refused", self.on_refused)
        cases = (
            (self.path("outside.txt"), "outside the root directory"),
            ("b.py", "does not match the patterns"),
            ("missing.txt", "does not exist"),
        )
        for text, reason in cases:
            with self.subTest(text=text):
                chooser.path_edit.set_edit_text(text)
                self.assertFalse(chooser.accept())
                self.assertEqual(reason, self.refused[-1][1])

    def test_outside_refusal_does_not_tell_whether_the_path_exists(self) -> None:
        self.make("inside/", "outside/secret.txt", "outside/locked/x.txt")
        chooser = urwid.FileChooser(self.root / "inside", root_dir=self.root / "inside", must_exist=False)
        urwid.connect_signal(chooser, "refused", self.on_refused)
        locked = self.path("outside", "locked", "x.txt")
        os_lstat = os.lstat

        def lstat(path: typing.Any, *args: typing.Any, **kwargs: typing.Any) -> os.stat_result:
            if os.fspath(path) == locked:
                raise PermissionError(errno.EACCES, "Permission denied", locked)
            return os_lstat(path, *args, **kwargs)

        typed = (
            self.path("outside", "secret.txt"),
            locked,
            self.path("outside", "missing.txt"),
            self.path("outside", "nodir", "x.txt"),
            os.path.join("..", "outside", "nodir", "x.txt"),
        )
        with mock.patch("os.lstat", side_effect=lstat):
            for text in typed:
                with self.subTest(text=text):
                    chooser.path_edit.set_edit_text(text)
                    self.assertFalse(chooser.accept())
                    self.assertEqual("outside the root directory", self.refused[-1][1])

    def test_unreadable_entry_refused(self) -> None:
        self.make("a.txt")
        chooser = self.chooser("a.txt")
        denied = FileEntry(
            "a.txt",
            self.path("a.txt"),
            None,
            FileKind.UNKNOWN,
            error=PermissionError(errno.EACCES, "Permission denied"),
        )
        with mock.patch.object(DirectoryReader, "entry", return_value=denied):
            self.assertFalse(chooser._accept_paths([self.path("a.txt")]))
        self.assertEqual("cannot be read: Permission denied", self.refused[-1][1])

    def test_typed_new_name(self) -> None:
        self.make("dir/", "file.txt")
        chooser = self.chooser(must_exist=False, patterns=("*.txt",))
        cases = (
            ("new.txt", None),
            ("new.py", "cannot be selected"),
            ("nodir" + SEP + "new.txt", "the parent directory does not exist"),
            ("file.txt" + SEP + "new.txt", "cannot be read: " + os.strerror(errno.ENOTDIR)),
            ("newdir" + SEP, "is not a file name"),
            (".hidden.txt", None),
        )
        for text, reason in cases:
            with self.subTest(text=text):
                self.refused.clear()
                chooser.path_edit.set_edit_text(text)
                self.assertEqual(reason is None, chooser.accept())
                self.assertEqual([] if reason is None else [reason], [item[1] for item in self.refused])

    def test_show_does_not_refuse_a_typed_name(self) -> None:
        self.make("report.txt")
        chooser = self.chooser(show=lambda entry: not entry.name.startswith("r"), patterns=("*.txt",))
        self.assertNotIn("report.txt", self.names(chooser))
        chooser.path_edit.set_edit_text("report.txt")
        self.assertTrue(chooser.accept())
        self.assertEqual([], self.refused)

    def test_select_predicate_gets_new_file_entry(self) -> None:
        self.make("a.txt")
        seen: list[FileEntry] = []

        def select(entry: FileEntry) -> bool:
            seen.append(entry)
            return entry.kind == FileKind.FILE

        chooser = self.chooser(must_exist=False, select=select)
        chooser.path_edit.set_edit_text("new.txt")
        self.assertTrue(chooser.accept())
        self.assertFalse(seen[-1].exists)
        self.assertEqual(FileKind.FILE, seen[-1].kind)

    def test_veto(self) -> None:
        self.make("a.txt")
        chooser = self.chooser("a.txt")
        self.veto = True
        self.assertFalse(chooser.accept())
        self.assertEqual(1, len(self.accepted))
        self.assertEqual(self.path("a.txt"), self.field(chooser)[0])

    def test_vanished_row_file_is_not_a_new_name(self) -> None:
        self.make("a.txt", "b.txt")
        for route in ("ok", "enter in field", "activation"):
            with self.subTest(route=route):
                (self.root / "b.txt").touch()
                self.refused.clear()
                chooser = self.chooser(must_exist=False)
                self.focus_list(chooser, "b.txt")
                (self.root / "b.txt").unlink()
                if route == "ok":
                    self.assertFalse(chooser.accept())
                elif route == "activation":
                    press(chooser, SIZE, "enter")
                else:
                    chooser._w.focus_position = 0
                    press(chooser, SIZE, "enter")
                self.assertEqual("does not exist", self.refused[-1][1])
        press(chooser, SIZE, "backspace", "t")
        self.assertTrue(chooser.accept())
        self.assertEqual((pathlib.Path(self.path("b.txt")),), self.accepted[-1])

    @unittest.skipUnless(HAS_SYMLINKS, "symbolic links are needed")
    def test_dangling_link_is_not_a_new_name(self) -> None:
        os.symlink("nowhere", self.path("dangling"))
        chooser = self.chooser(must_exist=False)
        chooser.path_edit.set_edit_text("dangling")
        self.assertFalse(chooser.accept())
        self.assertTrue(self.refused[-1][1].startswith("cannot be read"))

    @unittest.skipUnless(HAS_SYMLINKS, "symbolic links are needed")
    def test_escaping_links_refused(self) -> None:
        self.make("inside/", "outside/secret.txt")
        os.symlink(self.path("outside"), self.path("inside", "escape"))
        chooser = urwid.FileChooser(self.root / "inside", root_dir=self.root / "inside")
        urwid.connect_signal(chooser, "refused", self.on_refused)
        chooser.path_edit.set_edit_text("escape" + SEP + "secret.txt")
        self.assertFalse(chooser.accept())
        self.assertEqual("outside the root directory", self.refused[-1][1])
        self.assertEqual(self.path("inside"), chooser.current_dir)


class TestMultiple(ChooserTestCase):
    def test_marks_across_directories(self) -> None:
        self.make("a.txt", "sub/b.txt")
        chooser = self.chooser(multiple=True)
        changes: list[tuple[pathlib.Path, ...]] = []
        urwid.connect_signal(chooser, "selection changed", lambda _chooser, selection: changes.append(selection))
        self.focus_list(chooser, "a.txt")
        press(chooser, SIZE, " ")
        self.focus_list(chooser, "sub")
        press(chooser, SIZE, "enter")
        self.focus_list(chooser, "b.txt")
        press(chooser, SIZE, "insert")
        expected = (pathlib.Path(self.path("a.txt")), pathlib.Path(self.path("sub", "b.txt")))
        self.assertEqual(expected, chooser.selection)
        self.assertEqual(2, len(changes))
        self.assertIn("2 selected", "\n".join(render_text(chooser, SIZE)))
        self.assertTrue(chooser.accept())
        self.assertEqual([expected], self.accepted)

    def test_unmarked_activated_row_is_not_added(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser(multiple=True)
        self.focus_list(chooser, "a.txt")
        press(chooser, SIZE, " ")
        self.focus_list(chooser, "b.txt")
        press(chooser, SIZE, "enter")
        self.assertEqual([(pathlib.Path(self.path("a.txt")),)], self.accepted)

    def test_vanished_mark_refused(self) -> None:
        self.make("a.txt")
        for must_exist in (True, False):
            with self.subTest(must_exist=must_exist):
                (self.root / "a.txt").touch()
                chooser = self.chooser(multiple=True, must_exist=must_exist)
                self.focus_list(chooser, "a.txt")
                press(chooser, SIZE, " ")
                (self.root / "a.txt").unlink()
                self.assertFalse(chooser.accept())
                self.assertEqual("does not exist", self.refused[-1][1])
                self.assertEqual(1, len(chooser.selection))

    def test_mark_key_on_header_marks_nothing(self) -> None:
        self.make("a.txt")
        chooser = self.chooser(multiple=True)
        self.focus_list(chooser, "a.txt")
        press(chooser, SIZE, "up")
        self.assertIsNotNone(chooser.table.header_column)
        press(chooser, SIZE, "insert")
        self.assertEqual((), chooser.selection)

    def test_save_as_without_marks(self) -> None:
        self.make("a.txt")
        chooser = self.chooser(multiple=True, must_exist=False)
        self.type_text(chooser, "new.txt")
        self.assertTrue(chooser.accept())
        self.assertEqual([(pathlib.Path(self.path("new.txt")),)], self.accepted)

    def test_marks_need_multiple(self) -> None:
        self.make("a.txt", "b.txt")
        chooser = self.chooser()
        before = render_text(chooser, SIZE)
        chooser.select_all()
        chooser.clear_selection()
        self.assertEqual((), chooser.selection)
        self.assertEqual(before, render_text(chooser, SIZE))
        self.assertFalse(chooser.toggle_mark())

    def test_dot_row_never_shows_a_mark(self) -> None:
        self.make("sub/x/")
        chooser = self.chooser(select=FileKind.DIRECTORY, multiple=True)
        self.focus_list(chooser, "sub")
        press(chooser, SIZE, " ", "right")
        self.assertEqual(self.path("sub"), chooser.current_dir)
        self.assertEqual(1, len(chooser.selection))
        dot = next(row for row in chooser.table.body if row.data is not None and row.data.name == ".")
        self.assertEqual("", dot.cells[0].text)
        self.assertIsNone(dot.attr)

    def test_select_all_and_clear(self) -> None:
        self.make("a.txt", "b.txt", "dir/")
        chooser = self.chooser(multiple=True)
        chooser.select_all()
        self.assertEqual({"a.txt", "b.txt"}, {path.name for path in chooser.selection})
        chooser.clear_selection()
        self.assertEqual((), chooser.selection)


class TestLifetime(ChooserTestCase):
    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting")
    def test_chooser_is_freed_by_reference_counting(self) -> None:
        # a strong reference from a signal handler would only make a cycle, which gc.collect() also frees,
        # so the chooser has to go with the cyclic collector off
        self.make("a.txt")
        chooser = self.chooser()
        urwid.disconnect_signal(chooser, "accept", self.on_accept)
        urwid.disconnect_signal(chooser, "refused", self.on_refused)
        ref = weakref.ref(chooser)
        completer = weakref.ref(chooser.path_edit.text_completer)
        gc.disable()
        self.addCleanup(gc.enable)
        del chooser
        self.assertIsNone(ref())
        self.assertIsNone(completer())


if __name__ == "__main__":
    unittest.main()
