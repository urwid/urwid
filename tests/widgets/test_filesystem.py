"""Tests of FileKind, FileEntry, DirectoryReader and PathCompleter on a temporary tree."""

from __future__ import annotations

import errno
import os
import pathlib
import shutil
import sys
import tempfile
import typing
import unittest
from unittest import mock

import urwid
from urwid.testing import press
from urwid.widget import DirectoryReader, FileEntry

FileKind = urwid.FileKind
SEP = os.sep
HAS_SYMLINKS = hasattr(os, "symlink") and sys.platform != "win32"


class TreeTestCase(unittest.TestCase):
    """A temporary tree, resolved so that paths compare equal to what the reader resolves."""

    def setUp(self) -> None:
        """Create an empty tree root."""
        self.root = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)

    def make(self, *names: str) -> None:
        """Create each name under the root: a directory when it ends with a separator, else an empty file."""
        for name in names:
            path = self.root / name
            if name.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

    def path(self, *parts: str) -> str:
        """Return the path of *parts* under the root, as a string."""
        return str(self.root.joinpath(*parts))


class CompleterTestCase(TreeTestCase):
    """Drive a PathCompleter through a real Edit."""

    def edit(self, text: str, *, completer: urwid.PathCompleter | None = None, pos: int | None = None) -> urwid.Edit:
        """Return an edit holding *text*, completing relative to the root."""
        if completer is None:
            completer = urwid.PathCompleter(base_dir=self.root)
        return urwid.Edit("", text, edit_pos=pos, text_completer=completer)

    def tab(self, edit: urwid.Edit, count: int = 1) -> list[str]:
        """Press Tab *count* times and return the keys the edit left unhandled."""
        return press(edit, (60,), *(["tab"] * count))


class TestFileKind(unittest.TestCase):
    def test_composites(self) -> None:
        for kind in (FileKind.BLOCK_DEVICE, FileKind.CHAR_DEVICE, FileKind.FIFO, FileKind.SOCKET):
            with self.subTest(kind=kind):
                self.assertIn(kind, FileKind.SPECIAL)
        for kind in FileKind:
            with self.subTest(kind=kind):
                self.assertIn(kind, FileKind.ANY)
        self.assertNotIn(FileKind.FILE, FileKind.SPECIAL)


class TestFileEntry(unittest.TestCase):
    def test_display_name_and_editable(self) -> None:
        cases = (
            ("plain.txt", "plain.txt", True),
            ("tab\there", "tab\ufffdhere", False),
            ("bad\udcffbyte", "bad\ufffdbyte", False),
            ("with space", "with space", True),
        )
        for name, display, editable in cases:
            with self.subTest(name=name):
                entry = FileEntry(name, name, None, FileKind.FILE)
                self.assertEqual(display, entry.display_name)
                self.assertEqual(editable, entry.editable)

    def test_name_key_is_natural_and_case_folded(self) -> None:
        names = ["file10", "File2", "file1", "a"]
        self.assertEqual(["a", "file1", "File2", "file10"], sorted(names, key=DirectoryReader.name_key))


class TestDirectoryReader(TreeTestCase):
    def test_read_applies_visibility(self) -> None:
        self.make("a.txt", "b.py", ".hidden.txt", "dir/")
        reader = DirectoryReader(patterns=("*.txt",))
        self.assertEqual({"a.txt", "dir"}, {entry.name for entry in reader.read(self.root)})
        self.assertEqual(
            {"a.txt", "dir", ".hidden.txt"},
            {entry.name for entry in reader.read(self.root, show_hidden=True)},
        )
        only_dirs = DirectoryReader(show=FileKind.DIRECTORY)
        self.assertEqual({"dir"}, {entry.name for entry in only_dirs.read(self.root)})
        predicate = DirectoryReader(show=lambda entry: entry.name.startswith("b"))
        self.assertEqual({"b.py", "dir"}, {entry.name for entry in predicate.read(self.root)})

    def test_entry_fields(self) -> None:
        self.make("dir/")
        (self.root / "data.bin").write_bytes(b"12345")
        entries = {entry.name: entry for entry in DirectoryReader().read(self.root)}
        data = entries["data.bin"]
        self.assertEqual(FileKind.FILE, data.kind)
        self.assertEqual(5, data.size)
        self.assertEqual(self.path("data.bin"), data.resolved)
        self.assertFalse(data.outside_root)
        self.assertEqual(FileKind.DIRECTORY, entries["dir"].kind)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are needed")
    def test_special_kind(self) -> None:
        self.make("plain")
        os.mkfifo(self.path("pipe"))
        entries = {entry.name: entry for entry in DirectoryReader(show=FileKind.SPECIAL).read(self.root)}
        self.assertEqual(["pipe"], list(entries))
        self.assertEqual(FileKind.FIFO, entries["pipe"].kind)

    def test_read_outside_root_is_refused_before_listing(self) -> None:
        self.make("inside/", "other/")
        reader = DirectoryReader(root_dir=self.root / "inside")
        with mock.patch.object(DirectoryReader, "scan", autospec=True) as scan:
            with self.assertRaises(PermissionError):
                reader.read(self.root / "other")
            with self.assertRaises(PermissionError):
                reader.read(self.root / "inside" / "..")
            scan.assert_not_called()

    def test_contains(self) -> None:
        self.make("inside/sub/")
        reader = DirectoryReader(root_dir=self.root / "inside")
        self.assertTrue(reader.contains(self.path("inside")))
        self.assertTrue(reader.contains(self.path("inside", "sub")))
        self.assertFalse(reader.contains(self.path("inside-other")))
        self.assertFalse(reader.contains(str(self.root)))
        self.assertTrue(DirectoryReader().contains(str(self.root)))
        with mock.patch("os.path.commonpath", side_effect=ValueError("different drives")):
            self.assertFalse(reader.contains("D:\\elsewhere"))

    def test_entry_missing(self) -> None:
        self.make("dir/")
        entry = DirectoryReader().entry(self.path("dir", "new.txt"))
        self.assertFalse(entry.exists)
        self.assertIsNone(entry.error)
        self.assertEqual(self.path("dir", "new.txt"), entry.resolved)
        orphan = DirectoryReader().entry(self.path("missing", "new.txt"))
        self.assertFalse(orphan.exists)
        self.assertIsNone(orphan.resolved)

    def test_entry_missing_under_outside_parent(self) -> None:
        self.make("inside/", "outside/")
        entry = DirectoryReader(root_dir=self.root / "inside").entry(self.path("outside", "new.txt"))
        self.assertFalse(entry.exists)
        self.assertTrue(entry.outside_root)

    def test_entry_absolute_outside(self) -> None:
        self.make("inside/", "outside.txt")
        entry = DirectoryReader(root_dir=self.root / "inside").entry(self.path("outside.txt"))
        self.assertTrue(entry.exists)
        self.assertTrue(entry.outside_root)
        self.assertEqual(FileKind.UNKNOWN, entry.kind)

    def test_nul_character_is_an_error_not_an_exception(self) -> None:
        reader = DirectoryReader()
        entry = reader.entry(self.path("a\0b"))
        self.assertEqual(errno.EINVAL, typing.cast("OSError", entry.error).errno)
        with self.assertRaises(OSError):
            reader.resolve(self.path("a\0b"))
        self.assertEqual([], urwid.PathCompleter(base_dir=self.root)("x\0" + SEP + "a", 4))

    def test_entry_unreadable(self) -> None:
        self.make("file.txt")
        denied = PermissionError(errno.EACCES, "denied")
        with mock.patch("os.lstat", side_effect=denied):
            entry = DirectoryReader().entry(self.path("file.txt"))
        self.assertIs(denied, entry.error)


@unittest.skipUnless(HAS_SYMLINKS, "symbolic links are needed")
class TestDirectoryReaderSymlinks(TreeTestCase):
    def setUp(self) -> None:
        """Create a root with links to inside and outside targets."""
        super().setUp()
        self.make("inside/real/file.txt", "outside/secret.txt")
        os.symlink(self.path("outside"), self.path("inside", "escape"))
        os.symlink(self.path("outside", "secret.txt"), self.path("inside", "secret-link"))
        os.symlink(self.path("inside", "real"), self.path("inside", "real-link"))
        os.symlink("nowhere", self.path("inside", "dangling"))
        self.reader = DirectoryReader(root_dir=self.root / "inside")

    def test_read_marks_outside_links_without_reading_targets(self) -> None:
        outside = self.path("outside")
        os_stat = os.stat
        read: list[str] = []

        def stat(path: typing.Any, *args: typing.Any, **kwargs: typing.Any) -> os.stat_result:
            if os.fspath(path).startswith(outside):
                read.append(os.fspath(path))
            return os_stat(path, *args, **kwargs)

        with mock.patch("os.stat", side_effect=stat):
            entries = {entry.name: entry for entry in self.reader.read(self.root / "inside")}
        self.assertEqual([], read)
        self.assertTrue(entries["escape"].outside_root)
        self.assertEqual(FileKind.UNKNOWN, entries["escape"].kind)
        self.assertTrue(entries["secret-link"].outside_root)
        self.assertEqual(FileKind.BROKEN_LINK, entries["dangling"].kind)
        self.assertIsNotNone(entries["dangling"].error)
        self.assertEqual("nowhere", entries["dangling"].link_target)

    def test_read_inside_link(self) -> None:
        entries = {entry.name: entry for entry in self.reader.read(self.root / "inside")}
        self.assertEqual(FileKind.DIRECTORY, entries["real-link"].kind)
        self.assertTrue(entries["real-link"].is_symlink)
        self.assertFalse(entries["real-link"].outside_root)

    def test_escaping_directory_link_is_never_scanned(self) -> None:
        with mock.patch.object(DirectoryReader, "scan", autospec=True) as scan, self.assertRaises(PermissionError):
            self.reader.read(self.root / "inside" / "escape")
        scan.assert_not_called()

    def test_entry_through_escaping_directory_link(self) -> None:
        entry = self.reader.entry(self.path("inside", "escape", "secret.txt"))
        self.assertTrue(entry.exists)
        self.assertTrue(entry.outside_root)
        self.assertEqual(FileKind.UNKNOWN, entry.kind)

    def test_outside_dangling_link_does_not_tell_whether_its_target_exists(self) -> None:
        os.symlink(self.path("outside", "missing.txt"), self.path("inside", "gone"))
        entries = {entry.name: entry for entry in self.reader.read(self.root / "inside")}
        for name in ("gone", "secret-link"):
            with self.subTest(name=name):
                self.assertTrue(entries[name].outside_root)
                self.assertEqual(FileKind.UNKNOWN, entries[name].kind)
                self.assertIsNone(entries[name].error)

    def test_entry_dangling_link_exists(self) -> None:
        entry = self.reader.entry(self.path("inside", "dangling"))
        self.assertTrue(entry.exists)
        self.assertEqual(FileKind.BROKEN_LINK, entry.kind)
        self.assertIsNotNone(entry.error)

    def test_target_vanishes_after_resolving(self) -> None:
        target = self.path("inside", "real", "file.txt")
        os.symlink(target, self.path("inside", "file-link"))
        os_stat = os.stat
        vanished = FileNotFoundError(errno.ENOENT, "gone")

        def stat(path: typing.Any, *args: typing.Any, **kwargs: typing.Any) -> os.stat_result:
            if os.fspath(path) == target:
                raise vanished
            return os_stat(path, *args, **kwargs)

        with mock.patch("os.stat", side_effect=stat):
            entry = self.reader.entry(self.path("inside", "file-link"))
            scanned = {item.name: item for item in self.reader.read(self.root / "inside")}
        self.assertIs(vanished, entry.error)
        self.assertTrue(entry.exists)
        self.assertIs(vanished, scanned["file-link"].error)

    def test_link_parent_is_the_parent_of_the_target(self) -> None:
        # POSIX resolves "real-link/.." through the link, to the parent of its target
        self.assertEqual(self.path("inside"), self.reader.resolve(self.path("inside", "real-link", "..")))
        os.symlink(self.path("outside"), self.path("inside", "real", "out"))
        self.assertFalse(self.reader.contains(self.reader.resolve(self.path("inside", "real", "out", ".."))))
        self.assertEqual(str(self.root), self.reader.resolve(self.path("inside", "real", "out", "..")))


class TestPathCompleter(CompleterTestCase):
    def test_unique_directory_in_one_tab(self) -> None:
        self.make("subdir/x", "file.txt")
        edit = self.edit("su")
        self.assertEqual([], self.tab(edit))
        self.assertEqual(("subdir" + SEP, 7), (edit.edit_text, edit.edit_pos))

    def test_unique_file_has_no_separator(self) -> None:
        self.make("subdir/x", "file.txt")
        edit = self.edit("fi")
        self.tab(edit)
        self.assertEqual(("file.txt", 8), (edit.edit_text, edit.edit_pos))
        self.assertEqual(["tab"], self.tab(edit))

    def test_common_prefix_then_cycle(self) -> None:
        self.make("report-1.txt", "report-2.txt", "other")
        edit = self.edit("re")
        self.tab(edit)
        self.assertEqual(("report-", 7), (edit.edit_text, edit.edit_pos))
        self.tab(edit)
        self.assertEqual("report-1.txt", edit.edit_text)
        self.tab(edit)
        self.assertEqual("report-2.txt", edit.edit_text)
        self.tab(edit)
        self.assertEqual("report-", edit.edit_text)

    def test_no_candidate_returns_tab(self) -> None:
        self.make("a.txt")
        self.assertEqual(["tab"], self.tab(self.edit("zz")))

    def test_mid_component_replaces_whole_component(self) -> None:
        self.make("alpha/", "beta.txt")
        edit = self.edit("alXX" + SEP + "rest", pos=2)
        self.tab(edit)
        self.assertEqual(("alpha" + SEP + "rest", 6), (edit.edit_text, edit.edit_pos))

    def test_mid_component_common_prefix_keeps_suffix(self) -> None:
        self.make("report-1", "report-2")
        edit = self.edit("reXX", pos=2)
        self.tab(edit)
        self.assertEqual(("report-XX", 7), (edit.edit_text, edit.edit_pos))

    def test_only_directories_before_later_components(self) -> None:
        self.make("data/", "data.txt")
        edit = self.edit("da" + SEP + "x", pos=2)
        self.tab(edit)
        self.assertEqual(("data" + SEP + "x", 5), (edit.edit_text, edit.edit_pos))

    def test_only_directories_option(self) -> None:
        self.make("data/", "data.txt")
        edit = self.edit("da", completer=urwid.PathCompleter(base_dir=self.root, only_directories=True))
        self.tab(edit)
        self.assertEqual("data" + SEP, edit.edit_text)

    def test_nested_and_absolute(self) -> None:
        self.make("one/two/three.txt")
        edit = self.edit("one" + SEP + "tw")
        self.tab(edit)
        self.assertEqual("one" + SEP + "two" + SEP, edit.edit_text)
        absolute = self.edit(self.path("one", "t"))
        self.tab(absolute)
        self.assertEqual(self.path("one", "two") + SEP, absolute.edit_text)

    def test_order_is_natural_and_sort_key_overrides(self) -> None:
        self.make("f10", "f9", "g1")
        edit = self.edit("f", completer=urwid.PathCompleter(base_dir=self.root))
        # natural order puts f9 first, where plain string order would put f10 first
        self.tab(edit)
        self.assertEqual("f9", edit.edit_text)
        reverse = urwid.PathCompleter(base_dir=self.root, sort_key=lambda entry: -len(entry.name))
        edit = self.edit("f", completer=reverse)
        self.tab(edit)
        self.assertEqual("f10", edit.edit_text)

    def test_hidden_only_with_a_dot(self) -> None:
        self.make(".config/", "cache/")
        edit = self.edit("c")
        self.tab(edit)
        self.assertEqual("cache" + SEP, edit.edit_text)
        dotted = self.edit(".c")
        self.tab(dotted)
        self.assertEqual(".config" + SEP, dotted.edit_text)

    def test_glob_characters_are_literal(self) -> None:
        # "[" is a glob character that every platform allows in a file name
        self.make("a[b].txt", "axb.txt")
        edit = self.edit("a[")
        self.tab(edit)
        self.assertEqual("a[b].txt", edit.edit_text)

    def test_tilde_is_kept(self) -> None:
        self.make("home/docs/")
        with mock.patch.dict(os.environ, {"HOME": self.path("home"), "USERPROFILE": self.path("home")}):
            edit = self.edit("~" + SEP + "do")
            self.tab(edit)
        self.assertEqual("~" + SEP + "docs" + SEP, edit.edit_text)

    def test_root_escape_by_parent_is_not_offered(self) -> None:
        self.make("inside/", "outside.txt")
        completer = urwid.PathCompleter(DirectoryReader(root_dir=self.root / "inside"), base_dir=self.root / "inside")
        with mock.patch.object(DirectoryReader, "scan", autospec=True) as scan:
            self.assertEqual(["tab"], self.tab(self.edit(".." + SEP + "out", completer=completer)))
            self.assertEqual(["tab"], self.tab(self.edit(self.path("out"), completer=completer)))
        scan.assert_not_called()

    def test_unreadable_directory_completes_nothing(self) -> None:
        self.make("a.txt")
        with mock.patch.object(DirectoryReader, "scan", side_effect=PermissionError(errno.EACCES, "denied")):
            self.assertEqual(["tab"], self.tab(self.edit("a")))

    @unittest.skipIf(sys.platform == "win32", "Windows file names cannot hold control characters")
    def test_non_editable_name_is_not_offered(self) -> None:
        self.make("tab\tname", "tame")
        edit = self.edit("ta")
        self.tab(edit)
        self.assertEqual("tame", edit.edit_text)

    def test_case_insensitive_common_start(self) -> None:
        # as on Windows: names match whatever their case, so the common start does too
        self.make("Readme", "README.txt")
        with mock.patch("os.path.normcase", str.lower):
            edit = self.edit("rea")
            self.tab(edit)
        self.assertEqual(("readme", 6), (edit.edit_text, edit.edit_pos))

    def test_base_dir_property(self) -> None:
        self.make("sub/file.txt")
        completer = urwid.PathCompleter(base_dir=self.root)
        completer.base_dir = self.root / "sub"
        self.assertEqual(self.path("sub"), completer.base_dir)
        edit = self.edit("fi", completer=completer)
        self.tab(edit)
        self.assertEqual("file.txt", edit.edit_text)


@unittest.skipUnless(HAS_SYMLINKS, "symbolic links are needed")
class TestPathCompleterSymlinks(CompleterTestCase):
    def test_outside_link_target_is_not_offered(self) -> None:
        self.make("inside/", "outside/")
        os.symlink(self.path("outside"), self.path("inside", "escape"))
        self.make("inside/esc.txt")
        completer = urwid.PathCompleter(DirectoryReader(root_dir=self.root / "inside"), base_dir=self.root / "inside")
        edit = self.edit("es", completer=completer)
        self.tab(edit)
        self.assertEqual("esc.txt", edit.edit_text)
        with mock.patch.object(DirectoryReader, "scan", autospec=True) as scan:
            self.assertEqual(["tab"], self.tab(self.edit("escape" + SEP, completer=completer)))
        scan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
