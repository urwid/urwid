"""Tests of the examples/edit.py editor: file round trips, the highlighter, the menus and the selection."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import typing
import unittest
from unittest import mock

import urwid
import urwid.testing

if typing.TYPE_CHECKING:
    import types

EXAMPLE: typing.Final = pathlib.Path(__file__).resolve().parent.parent / "edit.py"
SIZE: typing.Final = (80, 24)
TEXTS: typing.Final = {
    "no final newline": "def f():\n    return 1",
    "crlf": "x = 1\r\ny = 'two'\r\n",
    "trailing blank lines": "# comment\nprint(42)\n\n\n",
    "empty": "",
}


def load_example() -> types.ModuleType:
    """Import examples/edit.py by its path, without running it."""
    spec = importlib.util.spec_from_file_location("edit_example", EXAMPLE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {EXAMPLE}")
    module = importlib.util.module_from_spec(spec)
    # registered first, as importlib does: dataclasses resolve the module's string annotations through sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


edit = load_example()


def joined(markup: typing.Any) -> str:
    """Return the text of *markup*."""
    if isinstance(markup, str):
        return markup
    if isinstance(markup, tuple):
        return joined(markup[1])
    return "".join(joined(part) for part in markup)


class TestFileRoundTrip(unittest.TestCase):
    """Reading and writing a document keeps its bytes."""

    def setUp(self) -> None:
        """Create a temporary directory."""
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_bytes_written_equal_bytes_read(self) -> None:
        """An unchanged document is written back byte for byte, whatever its line endings."""
        cases = {
            "lf": b"one\ntwo\n",
            "crlf": b"one\r\ntwo\r\n",
            "cr": b"one\rtwo\r",
            "no final newline": b"one\ntwo",
            "empty": b"",
            "utf-8": "café\n".encode(),
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                source = self.root / f"{label}.txt"
                source.write_bytes(data)
                document = edit.read_document(source)
                self.assertNotIn("\r", document.text)
                self.assertFalse(document.mixed)
                target = self.root / f"{label}.out"
                edit.write_document(target, document.text, document.newline, exclusive=True)
                self.assertEqual(data, target.read_bytes())

    def test_mixed_endings_written_in_first_convention(self) -> None:
        """Mixed line endings are reported and written with the first one."""
        source = self.root / "mixed.txt"
        source.write_bytes(b"a\r\nb\nc\r")
        document = edit.read_document(source)
        self.assertTrue(document.mixed)
        self.assertEqual("\r\n", document.newline)
        edit.write_document(source, document.text, document.newline, exclusive=False)
        self.assertEqual(b"a\r\nb\r\nc\r\n", source.read_bytes())

    def test_invalid_utf8_refused(self) -> None:
        """A file that is not UTF-8 is refused."""
        source = self.root / "latin1.txt"
        source.write_bytes(b"caf\xe9\n")
        with self.assertRaises(UnicodeDecodeError):
            edit.read_document(source)

    def test_exclusive_write_refuses_existing_file(self) -> None:
        """An exclusive write leaves an existing file as it was."""
        target = self.root / "exists.txt"
        target.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            edit.write_document(target, "new", "\n", exclusive=True)
        self.assertEqual(b"keep", target.read_bytes())


class TestHighlighter(unittest.TestCase):
    """The pygments highlighter."""

    def setUp(self) -> None:
        """Skip without pygments."""
        if edit.lexer_for(None) is None:
            self.skipTest("pygments is not installed")

    def test_markup_joins_back_to_the_text(self) -> None:
        """The markup holds exactly the text it highlights."""
        lexer = edit.lexer_for(pathlib.Path("sample.py"))
        highlighter = edit.Highlighter(lexer)
        for label, text in TEXTS.items():
            with self.subTest(label=label):
                markup = highlighter(text)
                self.assertEqual(text, joined(markup))

    def test_edit_accepts_the_markup(self) -> None:
        """Edit renders with the highlighter's markup."""
        highlighter = edit.Highlighter(edit.lexer_for(pathlib.Path("sample.py")))
        for label, text in TEXTS.items():
            with self.subTest(label=label):
                widget = urwid.Edit(multiline=True, highlighter=highlighter)
                widget.set_edit_text(text)
                widget.render((40,))

    def test_keywords_are_coloured(self) -> None:
        """Keywords and strings get their palette entries."""
        markup = edit.Highlighter(edit.lexer_for(pathlib.Path("sample.py")))("def f(): return 'x'")
        self.assertIn(("keyword", "def"), markup)
        self.assertIn(("string", "'x'"), markup)


class TestMenuRouting(unittest.TestCase):
    """Keys that open, move between and close the menus of the menu bar."""

    def setUp(self) -> None:
        """Build the application without a loop, under a pop-up target as MainLoop(pop_ups=True) puts it."""
        self.app = edit.EditorApp(screen=mock.Mock(spec=urwid.display.raw.Screen))
        self.top = urwid.PopUpTarget(self.app.stack)
        self.top.render(SIZE, focus=True)
        self.file_menu, self.edit_menu = self.app.menu_bar.menus

    def send(self, key: str) -> None:
        """Send *key* as MainLoop does: to the top widget, then what comes back to unhandled_input."""
        if self.top.keypress(SIZE, key) is not None:
            self.app.unhandled_input(key)
        self.top.render(SIZE, focus=True)

    def open_menus(self) -> list[urwid.ActionMenu]:
        """Return the menus whose list is open."""
        return [menu for menu in self.app.menu_bar.menus if menu.pop_up_widget is not None]

    def check(self, owner: urwid.ActionMenu | None) -> None:
        """Assert that *owner* alone has its list open."""
        self.assertIs(owner, self.app.menu_bar.open_owner)
        self.assertEqual([] if owner is None else [owner], self.open_menus())

    def test_alt_shortcuts_and_f10(self) -> None:
        """Meta f, meta e and f10 open their menu, and esc closes it."""
        self.send("meta e")
        self.check(self.edit_menu)
        self.send("meta f")
        self.check(self.file_menu)
        self.send("esc")
        self.check(None)
        self.send("f10")
        self.check(self.file_menu)

    def test_arrows_move_the_open_list(self) -> None:
        """Left and right in an open list open the neighbouring menu."""
        self.send("meta f")
        self.send("right")
        self.check(self.edit_menu)
        self.send("left")
        self.check(self.file_menu)

    def test_launcher_keys(self) -> None:
        """Enter, space and down open the focused launcher's menu."""
        self.app.frame.focus_position = "header"
        for key in ("enter", " ", "down"):
            with self.subTest(key=key):
                self.send(key)
                self.check(self.file_menu)
                self.send("esc")
                self.check(None)

    def test_shortcuts_do_nothing_with_a_dialog_open(self) -> None:
        """The menu shortcuts are ignored while a dialog is open."""
        self.app.message("hello")
        self.top.render(SIZE, focus=True)
        self.send("meta f")
        self.check(None)

    def test_escape_gives_the_focus_back_to_the_text(self) -> None:
        """Esc closes the menu, then a second esc returns to the text."""
        self.send("meta f")
        self.send("esc")
        self.assertEqual("header", self.app.frame.focus_position)
        self.send("esc")
        self.assertEqual("body", self.app.frame.focus_position)

    def test_action_returns_focus_to_the_text(self) -> None:
        """Choosing an action returns the focus to the text."""
        self.send("meta e")
        self.send("u")
        self.assertEqual("body", self.app.frame.focus_position)


class TestDialogs(unittest.TestCase):
    """The Open and Save As dialogs and their messages."""

    def setUp(self) -> None:
        """Create a temporary directory and an application editing a new file in it."""
        self.root = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        self.app = edit.EditorApp(self.root / "new.txt", screen=mock.Mock(spec=urwid.display.raw.Screen))
        self.app.edit.set_edit_text("text\n")

    def messages(self) -> list[str]:
        """Return the text of every open dialog."""
        return ["".join(urwid.testing.render_text(level, (60, 8))) for level in self.app.stack.levels]

    def test_save_as_new_name(self) -> None:
        """Save As to a new name writes the file and closes the dialog."""

        def write(path: pathlib.Path) -> None:
            self.app.write(path, exclusive=True)

        chooser = self.app.file_dialog("Save as", must_exist=False, on_accept=write)
        chooser.path_edit.set_edit_text("saved.txt")
        chooser.accept()
        self.assertEqual(b"text\n", (self.root / "saved.txt").read_bytes())
        self.assertEqual(0, self.app.stack.depth)
        self.assertFalse(self.app.modified)

    def test_save_as_existing_asks_first(self) -> None:
        """Save As over an existing file writes it only after Yes."""
        target = self.root / "old.txt"
        for answer, expected in (("No", b"keep"), ("Yes", b"text\n")):
            with self.subTest(answer=answer):
                target.write_bytes(b"keep")
                self.app.save_as_dialog()
                chooser = self.app.stack.levels[-1].body
                chooser.path_edit.set_edit_text("old.txt")
                chooser.accept()
                self.assertEqual(2, self.app.stack.depth)
                self.app.stack.levels[-1].buttons[answer].keypress((10,), "enter")
                self.assertEqual(expected, target.read_bytes())
                self.app.close_dialogs()

    def test_write_error_is_shown_over_the_chooser(self) -> None:
        """A failed write is shown over the chooser, which stays open."""
        with mock.patch.object(edit, "write_document", side_effect=PermissionError(13, "Permission denied")):
            self.app.save_as_dialog()
            chooser = self.app.stack.levels[-1].body
            chooser.path_edit.set_edit_text("x.txt")
            chooser.accept()
        self.assertEqual(2, self.app.stack.depth)
        self.assertIn("Cannot write", self.messages()[-1])
        self.assertTrue(self.app.modified)

    def test_name_created_meanwhile_asks_first(self) -> None:
        """A name created since it was chosen leads to the overwrite question."""
        with mock.patch.object(edit, "write_document", side_effect=FileExistsError(17, "File exists")):
            self.app.save()
        self.assertEqual(1, self.app.stack.depth)
        self.assertIn("created meanwhile", self.messages()[-1])

    def test_failed_open_is_shown(self) -> None:
        """A file that cannot be opened is reported over the chooser."""
        (self.root / "latin1.txt").write_bytes(b"caf\xe9")
        self.app.open_dialog()
        chooser = self.app.stack.levels[-1].body
        chooser.path_edit.set_edit_text("latin1.txt")
        chooser.accept()
        self.assertEqual(2, self.app.stack.depth)
        self.assertIn("Cannot open", self.messages()[-1])

    def test_missing_directory_starts_in_the_working_directory(self) -> None:
        """A missing directory of the file starts the chooser in the working directory."""
        app = edit.EditorApp(self.root / "nodir" / "x.txt", screen=mock.Mock(spec=urwid.display.raw.Screen))
        with mock.patch("pathlib.Path.cwd", return_value=self.root):
            app.save_as_dialog()
        self.assertEqual(1, app.stack.depth)


class TestEditMenu(unittest.TestCase):
    """The Edit menu."""

    def test_undo_and_redo(self) -> None:
        """Undo and Redo from the Edit menu."""
        app = edit.EditorApp(screen=mock.Mock(spec=urwid.display.raw.Screen))
        top = urwid.PopUpTarget(app.stack)
        for key in ("a", "b", "meta e", "u"):
            if top.keypress(SIZE, key) is not None:
                app.unhandled_input(key)
            top.render(SIZE, focus=True)
        self.assertEqual("", app.edit.edit_text)
        for key in ("meta e", "r"):
            if top.keypress(SIZE, key) is not None:
                app.unhandled_input(key)
            top.render(SIZE, focus=True)
        self.assertEqual("ab", app.edit.edit_text)


class TestSelection(unittest.TestCase):
    """Mouse selection, and Cut and Copy from the Edit menu."""

    def setUp(self) -> None:
        """Build the application with a mock screen, and select "llo w" of "hello world" with a drag."""
        self.screen = mock.Mock(spec=urwid.display.raw.Screen)
        self.app = edit.EditorApp(screen=self.screen)
        self.app.edit.set_edit_text("hello world")
        self.app.edit.undo_limit = 10
        self.top = urwid.PopUpTarget(self.app.stack)
        self.top.render(SIZE, focus=True)
        _file_menu, self.edit_menu = self.app.menu_bar.menus

    def send(self, *keys: str) -> None:
        """Send *keys* as MainLoop does: to the top widget, then what comes back to unhandled_input."""
        for key in keys:
            if self.top.keypress(SIZE, key) is not None:
                self.app.unhandled_input(key)
            self.top.render(SIZE, focus=True)

    def select(self) -> None:
        """Drag over "llo w" on the first text row."""
        for event, col in (("mouse press", 2), ("mouse drag", 4), ("mouse release", 6)):
            self.top.mouse_event(SIZE, event, 1, col, 1, True)
            self.top.render(SIZE, focus=True)

    def enabled(self) -> dict[str, bool]:
        """Return whether Cut and Copy are enabled."""
        return {item.value: item.enabled for item in self.edit_menu.items if item and item.value in {"cut", "copy"}}

    def test_cut_and_copy_follow_the_selection(self) -> None:
        """Cut and Copy are enabled and the status counts the characters while text is selected."""
        self.assertEqual(self.enabled(), {"cut": False, "copy": False})
        self.select()
        self.assertEqual((self.app.edit.selected_text, self.enabled()), ("llo w", {"cut": True, "copy": True}))
        self.assertTrue(self.app.status.text.endswith("5 selected"))
        self.app.edit.set_edit_pos(0)
        self.assertEqual(self.enabled(), {"cut": False, "copy": False})
        self.assertFalse(self.app.status.text.endswith("selected"))

    def test_copy(self) -> None:
        """Copy puts the selected text on the clipboard and leaves the text alone."""
        self.select()
        self.send("meta e", "c")
        self.screen.copy_to_clipboard.assert_called_once_with("llo w")
        self.assertEqual(self.app.edit.edit_text, "hello world")

    def test_cut_is_one_undo_step(self) -> None:
        """Cut puts the text on the clipboard and removes it, as one step that Undo and Redo take."""
        self.select()
        self.send("meta e", "t")
        self.screen.copy_to_clipboard.assert_called_once_with("llo w")
        self.assertEqual((self.app.edit.edit_text, self.enabled()), ("heorld", {"cut": False, "copy": False}))
        self.send("meta e", "u")
        self.assertEqual(self.app.edit.edit_text, "hello world")
        self.send("meta e", "r")
        self.assertEqual(self.app.edit.edit_text, "heorld")


class TestStatus(unittest.TestCase):
    """The status line."""

    def test_cursor_column_counts_screen_columns(self) -> None:
        """The cursor column counts screen columns, so a wide character counts twice."""
        app = edit.EditorApp(screen=mock.Mock(spec=urwid.display.raw.Screen))
        app.edit.set_edit_text("a\n中文x", edit_pos=5)
        self.assertTrue(app.status.text.endswith("2:6"))


if __name__ == "__main__":
    unittest.main()
