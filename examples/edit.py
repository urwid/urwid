#!/usr/bin/env python3
#
# Urwid example: a text editor with a menu bar, file dialogs and syntax highlighting
#    Copyright (C) 2004-2009  Ian Ward
#    Copyright (C) 2026 Urwid developers
#
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
#
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "urwid>=5.3",
#     "pygments>=2.20",
# ]
# ///
"""Example: a text editor with a menu bar, Open and Save As dialogs, syntax highlighting and mouse selection.

The screen has a menu bar on the top row, the text in the middle and a status line on the bottom row.
The menus open with :kbd:`meta f` and :kbd:`meta e`, with :kbd:`f10`, or from the focused bar with :kbd:`enter`.
The whole file is read into one multiline :class:`urwid.Edit`.
A drag with the left mouse button selects text.
:menuselection:`Edit --> Copy` and :menuselection:`Edit --> Cut` are enabled while there is a selection.
They put it on the terminal's clipboard, which works in a terminal that accepts OSC 52 clipboard writes.
Not every terminal does: Konsole copies the text, the terminal of PyCharm does not.
The program cannot tell which case it was, because the terminal sends no reply.
The terminal's own selection needs its modifier key, usually :kbd:`shift`, while the editor runs.

The program reads and writes only the files chosen in its dialogs, as UTF-8.
A file with one kind of line ending is written back byte for byte when unchanged:
its line endings and its last newline are kept.
A file with mixed line endings is written with its first one; the status line says "mixed".
Highlighting needs ``pygments``; without it the Highlight item is disabled.
It exits with status 0 from :menuselection:`File --> Exit`, and with status 2 when the file given cannot be read.

Usage: ``edit.py [FILE]``
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import pathlib
import re
import sys
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pygments.lexer import Lexer

    from urwid.util import _TagMarkup

NEWLINE: typing.Final = re.compile(r"\r\n|\n|\r")
NEWLINE_NAMES: typing.Final = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}
# token types, most specific first, and the palette entry each one is drawn with
TOKEN_STYLES: typing.Final = (
    ("Comment", "comment"),
    ("Keyword", "keyword"),
    ("Name.Builtin", "builtin"),
    ("Literal.String", "string"),
    ("Literal.Number", "number"),
    ("Operator", "operator"),
    ("Error", "syntax error"),
)
PALETTE: typing.Final = [
    # name, 16 colours, background, monochrome, 256 colours, background
    ("menu", "black", "light gray", "standout", "black", "g85"),
    ("menu focus", "white", "dark blue", "bold,standout", "white", "#06c"),
    ("menu key", "dark red", "light gray", "underline", "#a00", "g85"),
    ("menu key focus", "yellow", "dark blue", "bold,underline,standout", "#fc6", "#06c"),
    ("menu disabled", "dark gray", "light gray", "", "g50", "g85"),
    ("text", "light gray", "black", "", "g85", "g11"),
    ("selected", "inherit", "dark blue", "standout", "inherit", "#036"),
    ("status", "black", "dark cyan", "standout", "black", "#6ac"),
    ("dialog", "black", "light gray", "", "black", "g85"),
    ("dialog shadow", "black", "black", "", "black", "black"),
    ("button", "black", "light gray", "", "black", "g78"),
    ("button focus", "white", "dark blue", "standout", "white", "#06c"),
    ("row focus", "white", "dark blue", "standout", "white", "#06c"),
    ("row marked", "black", "light cyan", "underline", "black", "#9cf"),
    ("field", "black", "light cyan", "underline", "black", "#cef"),
    ("field focus", "black", "white", "underline,bold", "black", "white"),
    ("dim", "dark gray", "light gray", "", "g50", "g85"),
    ("mark", "yellow", "light gray", "bold", "#a60", "g85"),
    ("error", "dark red", "light gray", "bold", "#a00", "g85"),
    ("keyword", "yellow", "black", "bold", "#fc6", "g11"),
    ("builtin", "light cyan", "black", "", "#6cf", "g11"),
    ("string", "light green", "black", "", "#9c6", "g11"),
    ("number", "light magenta", "black", "", "#c9f", "g11"),
    ("comment", "dark cyan", "black", "", "g54", "g11"),
    ("operator", "light gray", "black", "", "#fa8", "g11"),
    ("syntax error", "light red", "black", "bold", "#f66", "g11"),
]


@dataclasses.dataclass(frozen=True, slots=True)
class Document:
    """Text read from a file, with the line ending it is written back with."""

    #: The text with every line ending turned into ``\n``.
    text: str
    #: The first line ending of the file, ``\n`` for a file with none.
    newline: str = "\n"
    #: Whether the file had more than one kind of line ending; it is saved with :attr:`newline` alone.
    mixed: bool = False


def read_document(path: pathlib.Path) -> Document:
    """Read *path* as UTF-8 without translating line endings.

    :raises UnicodeDecodeError: the file is not valid UTF-8; nothing is replaced.
    :raises OSError: the file cannot be read.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        raw = stream.read()
    endings = {match.group() for match in NEWLINE.finditer(raw)}
    first = NEWLINE.search(raw)
    return Document(NEWLINE.sub("\n", raw), "\n" if first is None else first.group(), len(endings) > 1)


def write_document(path: pathlib.Path, text: str, newline: str, *, exclusive: bool) -> None:
    r"""Write *text* to *path* as UTF-8, with each ``\n`` turned into *newline*.

    :param path: the file to write
    :param text: the text, with ``\n`` line endings
    :param newline: the line ending written for each ``\n``
    :param exclusive: create the file, failing when it exists, instead of replacing it
    :raises FileExistsError: *exclusive* is set and the file exists.
    :raises OSError: the file cannot be written.
    """
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="") as stream:
        stream.write(text.replace("\n", newline))


@functools.lru_cache(maxsize=256)  # pygments has a few hundred token types
def token_style(token: tuple[str, ...]) -> str | None:
    """Return the palette entry of the pygments *token* type, ``None`` for text drawn plain."""
    dotted = ".".join(token)
    return next((name for prefix, name in TOKEN_STYLES if dotted == prefix or dotted.startswith(prefix + ".")), None)


class Highlighter:
    """Highlighter for :attr:`urwid.Edit.highlighter` that colours text with a ``pygments`` lexer.

    The markup is built from slices of the text itself, between the offsets the lexer reports,
    so it always joins back to exactly the text it was given.
    """

    __slots__ = ("lexer",)

    def __init__(self, lexer: Lexer) -> None:
        """Highlight with *lexer*."""
        self.lexer = lexer

    def __call__(self, text: str) -> _TagMarkup:
        """Return *text* as markup, coloured by token type, with adjacent runs of one colour joined."""
        runs: list[tuple[str | None, int, int]] = []  # (palette entry or None, start, end) of each run
        done = 0
        for offset, token, value in self.lexer.get_tokens_unprocessed(text):
            if offset < done:  # an offset the lexer reports out of order is left uncoloured
                continue
            end = min(offset + len(value), len(text))
            for style, start, stop in ((None, done, offset), (token_style(token), offset, end)):
                if start == stop:
                    continue
                if runs and runs[-1][0] == style:
                    runs[-1] = (style, runs[-1][1], stop)
                else:
                    runs.append((style, start, stop))
            done = end
        if done < len(text):
            runs.append((None, done, len(text)))
        return [text[start:stop] if style is None else (style, text[start:stop]) for style, start, stop in runs] or ""


def lexer_for(path: pathlib.Path | None) -> Lexer | None:
    """Return the ``pygments`` lexer for the name of *path*, plain text when none fits; ``None`` without pygments."""
    try:
        from pygments import lexers, util  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    if path is not None:
        try:
            return lexers.get_lexer_for_filename(path.name)
        except util.ClassNotFound:
            pass
    return lexers.get_lexer_by_name("text")


class BarMenu(urwid.ActionMenu):
    """A menu of the menu bar: its launcher is the bare label, with no indicator after it."""

    menu_indicator = urwid.Text("")

    def __init__(self, name: str, items: Sequence[urwid.MenuItem | None]) -> None:
        """Make the menu *name*, whose first letter is its Alt shortcut, with the list *items*."""
        super().__init__(
            [" ", ("menu key", name[0]), name[1:] + " "],
            items,
            open_keys=("enter", " ", "down"),
            pass_arrows_below=True,
            show_keys=True,
            attr_map="menu",
            focus_map="menu focus",
            disabled_map="menu disabled",
            launcher_focus_map={None: "menu focus", "menu key": "menu key focus"},
        )


class MenuBar(urwid.WidgetWrap[urwid.Columns]):
    """A row of :class:`urwid.ActionMenu` launchers that keeps exactly one list open while the user moves along it.

    :kbd:`left` and :kbd:`right` in an open list move to the neighbouring menu and open it.
    """

    def __init__(self, menus: Sequence[urwid.ActionMenu]) -> None:
        """Lay out *menus* left to right."""
        self.menus = tuple(menus)
        #: The launcher whose list is open, or ``None``.
        self.open_owner: urwid.ActionMenu | None = None
        for menu in self.menus:
            urwid.connect_signal(menu, "open", MenuBar._opened, weak_args=[self])
            urwid.connect_signal(menu, "close", MenuBar._closed, weak_args=[self])
        super().__init__(urwid.Columns([(urwid.PACK, menu) for menu in self.menus]))

    def _opened(self, menu: urwid.ActionMenu) -> None:
        """Record *menu* as the owner of the open list."""
        self.open_owner = menu

    def _closed(self, menu: urwid.ActionMenu) -> None:
        """Clear the owner, unless a newer list opened before *menu* sent its late close."""
        if self.open_owner is menu:
            self.open_owner = None

    def open_menu(self, index: int) -> None:
        """Focus the menu at *index* and open its list, closing any other open list first."""
        menu = self.menus[index]
        if self.open_owner is not None and self.open_owner is not menu:
            self.open_owner.close_pop_up()
        self._w.focus_position = index
        menu.open_pop_up()

    def keypress(self, size: tuple[int], key: str) -> str | None:  # type: ignore[override]
        """Move between menus; reopen the list on the newly focused menu when one was open."""
        owner = self.open_owner
        before = self._w.focus_position
        result = super().keypress(size, key)
        if owner is not None and self._w.focus_position != before:
            self.menus[self._w.focus_position].open_pop_up()
        return result


def _press(_button: urwid.Button, call: Callable[[], object]) -> None:
    """Call *call* for a button press."""
    call()


class Dialog(urwid.WidgetWrap[urwid.AttrMap[urwid.LineBox[urwid.Pile]]]):
    """A framed dialog: a body above a message line and a row of buttons."""

    def __init__(
        self,
        title: str,
        body: urwid.Widget,
        buttons: Sequence[tuple[str, Callable[[], object]]],
        *,
        extra: Sequence[urwid.Widget] = (),
    ) -> None:
        """Build the dialog; each button calls its function with no argument."""
        #: The widget above the message line.
        self.body = body
        #: The line that shows an error or a hint.
        self.message = urwid.Text("")
        #: The buttons by label.
        self.buttons = {label: urwid.Button(label, on_press=_press, user_data=call) for label, call in buttons}
        row = [urwid.AttrMap(button, "button", "button focus") for button in self.buttons.values()]
        columns = urwid.Columns([*((urwid.PACK, widget) for widget in extra), *((urwid.PACK, item) for item in row)])
        columns.dividechars = 2
        pile = urwid.Pile([(urwid.WEIGHT, 1, body), (urwid.PACK, self.message), (urwid.PACK, columns)])
        pile.select_navigation = True
        super().__init__(urwid.AttrMap(urwid.LineBox(pile, title), "dialog"))


class EditorApp:
    """The editor: its widgets, the open file and the actions of its menus."""

    def __init__(self, path: pathlib.Path | None = None, *, screen: urwid.display.raw.Screen) -> None:
        """Build the widgets for *screen*, then open *path* when given.

        :raises OSError: *path* exists and cannot be read.
        :raises UnicodeDecodeError: *path* is not valid UTF-8.
        """
        #: The screen whose clipboard Copy and Cut write to.
        self.screen = screen
        self.path: pathlib.Path | None = None
        #: Whether :attr:`path` was read from or written to; a new name is created exclusively on its first save.
        self.on_disk = False
        self.document = Document("")
        self.modified = False
        self.lexer: Lexer | None = None
        self.edit = urwid.Edit(
            multiline=True,
            allow_tab=True,
            undo_limit=200,
            mouse_select=True,
            select_attr="selected",
        )
        self.status = urwid.Text("")
        available = lexer_for(None) is not None
        highlight = urwid.MenuItem(
            "Highlight" if available else "Highlight (needs pygments)",
            "highlight",
            key="h",
            enabled=available,
        )
        file_menu = BarMenu(
            "File",
            [
                urwid.MenuItem("Open...", "open", key="o"),
                urwid.MenuItem("Save", "save", key="s"),
                urwid.MenuItem("Save as...", "save as", key="a"),
                None,
                urwid.MenuItem("Exit", "exit", key="x"),
            ],
        )
        edit_menu = BarMenu(
            "Edit",
            [
                urwid.MenuItem("Undo", "undo", key="u"),
                urwid.MenuItem("Redo", "redo", key="r"),
                None,
                urwid.MenuItem("Cut", "cut", key="t", enabled=False),
                urwid.MenuItem("Copy", "copy", key="c", enabled=False),
                None,
                highlight,
            ],
        )
        for menu in (file_menu, edit_menu):
            urwid.connect_signal(menu, "action", self.on_action)
        self.edit_menu = edit_menu
        self.menu_bar = MenuBar([file_menu, edit_menu])
        body = urwid.AttrMap(urwid.ListBox([self.edit]), "text")
        self.frame = urwid.Frame(
            body,
            header=urwid.AttrMap(self.menu_bar, "menu"),
            footer=urwid.AttrMap(self.status, "status"),
            focus_part="body",
        )
        self.stack = urwid.OverlayStack(self.frame)
        urwid.connect_signal(self.edit, "postchange", self.on_text_changed)
        urwid.connect_signal(self.edit, "edit_pos", self.on_cursor_moved)
        urwid.connect_signal(self.edit, "highlight", self.on_selection_changed)
        if path is not None:
            self.load(path, missing_ok=True)
        self.update_status()

    # --- state

    def load(self, path: pathlib.Path, *, missing_ok: bool = False) -> None:
        """Show the file *path*; a missing *path* with *missing_ok* starts an empty buffer under that name.

        :raises OSError: the file cannot be read.
        :raises UnicodeDecodeError: the file is not valid UTF-8.
        """
        on_disk = True
        try:
            document = read_document(path)
        except FileNotFoundError:
            if not missing_ok:
                raise
            document, on_disk = Document(""), False
        self.path, self.document, self.on_disk = path, document, on_disk
        self.edit.set_edit_text(document.text, edit_pos=0)
        self.modified = False
        self.choose_lexer()
        self.update_status()

    def choose_lexer(self) -> None:
        """Pick the lexer for the file name, and re-apply highlighting when it is on."""
        self.lexer = lexer_for(self.path)
        if self.edit.highlighter is not None and self.lexer is not None:
            self.edit.highlighter = Highlighter(self.lexer)

    def on_text_changed(self, _edit: urwid.Edit, _old: str) -> None:
        """Mark the buffer as modified."""
        self.modified = self.edit.edit_text != self.document.text
        self.update_status()

    def on_cursor_moved(self, _edit: urwid.Edit, _old: int, _new: int) -> None:
        """Show the new cursor position."""
        self.update_status()

    def on_selection_changed(
        self,
        _edit: urwid.Edit,
        _old: tuple[int, int] | None,
        new: tuple[int, int] | None,
    ) -> None:
        """Enable Cut and Copy while there is a selection, and show its size."""
        self.edit_menu.items = [
            dataclasses.replace(item, enabled=new is not None)
            if item is not None and item.value in {"cut", "copy"}
            else item
            for item in self.edit_menu.items
        ]
        self.update_status()

    def update_status(self) -> None:
        """Show the file name, the modified mark, the line endings, the lexer, the cursor and the selection size."""
        text, pos = self.edit.edit_text, self.edit.edit_pos
        start = text.rfind("\n", 0, pos) + 1
        line = text.count("\n", 0, pos) + 1
        column = urwid.calc_width(text, start, pos) + 1
        parts = [
            str(self.path) if self.path is not None else "(new file)",
            "*" if self.modified else " ",
            NEWLINE_NAMES[self.document.newline] + (" mixed" if self.document.mixed else ""),
            (self.lexer.name if self.lexer is not None else "plain") + ("" if self.edit.highlighter else " (off)"),
            f"{line}:{column}",
            *([f"{len(self.edit.selected_text)} selected"] if self.edit.highlight else []),
        ]
        self.status.set_text("  ".join(parts))

    # --- menus and keys

    def on_action(self, _menu: urwid.ActionMenu, item: urwid.MenuItem) -> None:
        """Give the focus back to the text, then run the menu action *item*."""
        self.frame.focus_position = "body"
        match item.value:
            case "open":
                self.unless_modified(self.open_dialog)
            case "save":
                self.save()
            case "save as":
                self.save_as_dialog()
            case "exit":
                self.unless_modified(self.exit)
            case "undo":
                self.edit.undo()
            case "redo":
                self.edit.redo()
            case "copy":
                self.screen.copy_to_clipboard(self.edit.selected_text)
            case "cut":
                self.screen.copy_to_clipboard(self.edit.selected_text)
                with self.edit.editing():  # one step of the undo history
                    self.edit.insert_text("")
            case "highlight":
                self.toggle_highlight()
            case _:
                raise ValueError(f"unknown menu action {item.value!r}")

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Open menus by their shortcuts, and give Esc back to the text; nothing while a dialog is open."""
        if self.stack.depth > 0 or not isinstance(key, str):
            return None
        match key:
            case "meta f" | "f10":
                self.frame.focus_position = "header"
                self.menu_bar.open_menu(0)
            case "meta e":
                self.frame.focus_position = "header"
                self.menu_bar.open_menu(1)
            case "esc" if self.menu_bar.open_owner is None:
                self.frame.focus_position = "body"
            case _:
                return None
        return True

    def toggle_highlight(self) -> None:
        """Switch highlighting on or off."""
        if self.edit.highlighter is None and self.lexer is not None:
            self.edit.highlighter = Highlighter(self.lexer)
        else:
            self.edit.highlighter = None
        self.update_status()

    def exit(self) -> None:
        """Stop the program."""
        raise urwid.ExitMainLoop

    # --- dialogs

    def ask(self, question: str, on_yes: Callable[[], object]) -> None:
        """Ask a yes or no *question*; *on_yes* runs after the dialog closes on Yes."""

        def answer(yes: bool) -> None:
            self.stack.close(widget=dialog)
            if yes:
                on_yes()

        dialog = Dialog(
            "Confirm",
            urwid.Filler(urwid.Text(question)),
            [("Yes", lambda: answer(True)), ("No", lambda: answer(False))],
        )
        self.stack.open(dialog, width=50, height=8)

    def unless_modified(self, action: Callable[[], object]) -> None:
        """Run *action*, after asking to discard the unsaved edits when there are some."""
        if self.modified:
            self.ask("The text has unsaved changes. Discard them?", action)
        else:
            action()

    def file_dialog(
        self,
        title: str,
        *,
        must_exist: bool,
        on_accept: Callable[[pathlib.Path], object],
    ) -> urwid.FileChooser:
        """Open a file chooser dialog that calls *on_accept* with the path chosen.

        The dialog stays open under whatever *on_accept* opens, such as an error message;
        :meth:`close_dialogs` closes it once the action succeeded.

        :returns: the chooser of the dialog.
        """
        # the chooser refuses a start path whose directory is gone, such as a new file's missing directory
        has_directory = self.path is not None and self.path.parent.is_dir()
        start = self.path if has_directory else pathlib.Path.cwd()
        chooser = urwid.FileChooser(
            start,
            must_exist=must_exist,
            caption="File: ",
            field_attr="field",
            field_focus_attr="field focus",
            focus_attr="row focus",
            unfocused_focus_attr="row marked",
            dim_attr="dim",
            mark_attr="mark",
            error_attr="error",
            header_focus_attr="row focus",
        )
        hidden = urwid.CheckBox(
            "Show hidden", on_state_change=lambda _box, state: setattr(chooser, "show_hidden", state)
        )

        def accepted(_chooser: urwid.FileChooser, paths: tuple[pathlib.Path, ...]) -> bool:
            on_accept(paths[0])
            return True  # the chooser itself never closes: a success closes every dialog, a failure shows above it

        dialog = Dialog(
            title,
            chooser,
            [("OK", chooser.accept), ("Cancel", lambda: self.stack.close(widget=dialog))],
            extra=[hidden],
        )
        urwid.connect_signal(chooser, "accept", accepted)

        def refused(_chooser: urwid.FileChooser, path: str, reason: str) -> None:
            dialog.message.set_text(("error", f"{path}: {reason}"))

        urwid.connect_signal(chooser, "refused", refused)
        self.stack.open(dialog, width=100, height=30)  # an overlay shrinks a size larger than the screen
        return chooser

    def open_dialog(self) -> None:
        """Choose a file and show it."""

        def chosen(path: pathlib.Path) -> None:
            try:
                self.load(path)
            except (OSError, UnicodeDecodeError) as exc:
                self.message(f"Cannot open {path}: {exc}")
            else:
                self.close_dialogs()

        self.file_dialog("Open", must_exist=True, on_accept=chosen)

    def save(self) -> None:
        """Write the buffer back to its file, or ask for a name when it has none."""
        if self.path is None:
            self.save_as_dialog()
        else:
            self.write(self.path, exclusive=not self.on_disk)

    def save_as_dialog(self) -> None:
        """Choose a name and write the buffer to it, asking before an existing file is replaced."""

        def chosen(path: pathlib.Path) -> None:
            if path.exists():
                self.ask(f"{path} exists. Replace it?", lambda: self.write(path, exclusive=False))
            else:
                self.write(path, exclusive=True)

        self.file_dialog("Save as", must_exist=False, on_accept=chosen)

    def write(self, path: pathlib.Path, *, exclusive: bool) -> None:
        """Write the buffer to *path*; a name that appeared since it was chosen goes to the overwrite question."""
        try:
            write_document(path, self.edit.edit_text, self.document.newline, exclusive=exclusive)
        except FileExistsError:
            self.ask(f"{path} was created meanwhile. Replace it?", lambda: self.write(path, exclusive=False))
            return
        except OSError as exc:
            self.message(f"Cannot write {path}: {exc}")
            return
        self.close_dialogs()
        renamed = path != self.path
        self.path, self.on_disk = path, True
        self.document = Document(self.edit.edit_text, self.document.newline)
        self.modified = False
        if renamed:
            self.choose_lexer()
        self.update_status()

    def close_dialogs(self) -> None:
        """Close every open dialog."""
        while self.stack.close():
            pass

    def message(self, text: str) -> None:
        """Show *text* in a dialog with an OK button."""
        dialog = Dialog("Message", urwid.Filler(urwid.Text(text)), [("OK", lambda: self.stack.close(widget=dialog))])
        self.stack.open(dialog, width=60, height=8)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Edit a text file.")
    parser.add_argument("file", nargs="?", type=pathlib.Path, help="the file to edit; a missing one is created on save")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the editor and return the exit status."""
    args = parse_args(argv)
    screen = urwid.display.raw.Screen()
    try:
        app = EditorApp(args.file, screen=screen)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Cannot open {args.file}: {exc}", file=sys.stderr)
        return 2
    urwid.MainLoop(app.stack, PALETTE, screen, pop_ups=True, unhandled_input=app.unhandled_input).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
