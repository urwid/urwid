#!/usr/bin/env python
#
# Urwid example similar to dialog(1) program
#    Copyright (C) 2004-2009  Ian Ward
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

"""Urwid example similar to dialog(1) program."""

from __future__ import annotations

import sys
import typing

import urwid
from urwid.command_map import Command

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Sequence

    from urwid.util import _TagMarkup

    _Width: typing.TypeAlias = int | tuple[typing.Literal[urwid.WHSettings.RELATIVE], int]
    _Height: typing.TypeAlias = int | typing.Literal[urwid.WHSettings.PACK]
    _ListItem: typing.TypeAlias = "urwid.CheckBox | MenuItem"


class DialogExit(Exception):
    """Raised by a dialog button or key handler to end the main loop with an exit code."""


class ExitButton(urwid.Button):
    """Button that carries the exit code `DialogDisplay.button_press` raises `DialogExit` with."""

    def __init__(
        self,
        label: _TagMarkup,
        on_press: typing.Callable[[ExitButton], typing.NoReturn],
        exitcode: int,
    ) -> None:
        """Initialize with the exit code raised by `DialogDisplay.button_press` on press."""
        super().__init__(label, on_press)
        self.exitcode = exitcode


class BodyScrollingPile(urwid.Pile):
    """Pile that scrolls its first item with the arrow and page keys while another item has the focus."""

    #: Commands whose keys scroll the first item, looked up through the widget's command map.
    scroll_commands: typing.ClassVar[frozenset[Command]] = frozenset(
        (
            Command.UP,
            Command.DOWN,
            Command.PAGE_UP,
            Command.PAGE_DOWN,
        )
    )

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Pass a scroll key to the first item and keep the focus where it is.

        :returns: for a scroll key while another item has the focus, what the first item returns;
            for any other key, what :meth:`Pile.keypress` returns.
        """
        if self._command_map[key] in self.scroll_commands and self.focus_position != 0:
            _widths, _heights, size_args = self.get_rows_sizes(size, focus=True)
            # The dialog builds the first item as a Pile, which takes a box or a flow size.
            first = typing.cast("urwid.Pile", self.contents[0][0])
            return first.keypress(typing.cast("tuple[int] | tuple[int, int]", size_args[0]), key)
        return super().keypress(size, key)


class DialogDisplay:
    """Base dialog widget: a bordered, shadowed frame with an optional header and a button footer.

    A height of 0 sizes the dialog to its content, and shrinks it to the screen when the content is taller.
    A long list then scrolls inside the dialog.
    """

    #: The Pile that holds the header and body above the buttons.
    frame_class: typing.ClassVar[type[urwid.Pile]] = urwid.Pile

    palette: typing.ClassVar[list[tuple[str, str, str] | tuple[str, str, str, str]]] = [
        ("body", "black", "light gray", "standout"),
        ("border", "black", "dark blue"),
        ("shadow", "white", "black"),
        ("selectable", "black", "dark cyan"),
        ("focus", "white", "dark blue", "bold"),
        ("focustext", "light gray", "dark blue"),
    ]

    def __init__(
        self,
        text: _TagMarkup | None,
        height: int | str,
        width: int | str,
        body: urwid.Widget | None = None,
    ) -> None:
        """Initialize the bordered, shadowed dialog frame around `body`, with an optional header from `text`."""
        raw_width = int(width)
        parsed_width: _Width = raw_width if raw_width > 0 else (urwid.RELATIVE, 80)
        raw_height = int(height)
        parsed_height: _Height = raw_height if raw_height > 0 else urwid.PACK

        self.body = body
        if body is None:
            # fill space with nothing
            body = urwid.Filler(urwid.Divider(), urwid.TOP)

        # Every layer is a Pile rather than a Frame: a Frame is a box widget only, while a Pile with a weighted item
        # is a box and a flow widget, so the dialog can take the rows of its content.
        # The header and the body share the weighted item, so a dialog that is too short keeps its buttons.
        content = urwid.Pile([("weight", 1, body)])
        if text is not None:
            content.contents.insert(0, (urwid.Pile([urwid.Text(text), urwid.Divider()]), content.options(urwid.PACK)))
            content.focus_position = 1
        self.frame = self.frame_class([("weight", 1, content)])
        self.body_position = 0
        self.footer_position: int | None = None
        # Exit code of the first button. A dialog can exit with it when no widget handles Enter.
        self.default_exitcode: int | None = None
        self.focus_part: typing.Literal["body", "footer"] = "footer"
        w: urwid.Widget = self.frame

        # pad area around listbox
        w = urwid.Padding(w, urwid.LEFT, left=2, right=2)
        w = urwid.Pile([("pack", urwid.Divider()), ("weight", 1, w), ("pack", urwid.Divider())], focus_item=1)
        w = urwid.AttrMap(w, "body")

        # "shadow" effect
        shadow = urwid.AttrMap(urwid.Filler(urwid.Text(("border", "  ")), urwid.TOP), "shadow")
        w = urwid.Columns([w, (2, shadow)], box_columns=[1])
        w = urwid.Pile([("weight", 1, w), ("pack", urwid.AttrMap(urwid.Text(("border", "  ")), "shadow"))])

        # outermost border area
        w = urwid.Padding(w, urwid.CENTER, parsed_width)
        w = urwid.Filler(w, urwid.MIDDLE, parsed_height, shrink_to_fit=True)
        w = urwid.AttrMap(w, "border")

        self.view: urwid.Widget = w

    def add_buttons(self, buttons: Sequence[tuple[str, int]]) -> None:
        """Set the row of buttons in the dialog's footer, each raising `DialogExit` with its exit code."""
        lines = [
            urwid.AttrMap(ExitButton(name, self.button_press, exitcode), "selectable", "focus")
            for name, exitcode in buttons
        ]
        self.buttons = urwid.GridFlow(lines, 10, 3, 1, urwid.CENTER)
        self.default_exitcode = buttons[0][1] if buttons else None
        footer = (urwid.Pile([urwid.Divider(), self.buttons], focus_item=1), self.frame.options(urwid.PACK))
        if self.footer_position is None:
            self.frame.contents.append(footer)
            self.footer_position = len(self.frame.contents) - 1
        else:
            self.frame.contents[self.footer_position] = footer
        self.set_focus_part(self.focus_part)

    def set_focus_part(self, part: typing.Literal["body", "footer"]) -> None:
        """Move the focus to the body or to the buttons, and keep the choice for buttons added later."""
        self.focus_part = part
        position = self.body_position if part == "body" else self.footer_position
        if position is not None:
            self.frame.focus_position = position

    def button_press(self, button: ExitButton) -> typing.NoReturn:
        """Raise `DialogExit` with the pressed button's exit code."""
        raise DialogExit(button.exitcode)

    def main(self) -> tuple[int, str]:
        """Run the dialog's main loop and return its exit code and message."""
        self.loop: urwid.MainLoop = urwid.MainLoop(self.view, self.palette, unhandled_input=self.unhandled_input)
        try:
            self.loop.run()
        except DialogExit as e:
            return self.on_exit(e.args[0])
        raise AssertionError("unreachable: MainLoop.run() returned without raising DialogExit")

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Leave input that no widget handled unhandled."""
        return None

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """Return the exit code together with an empty message."""
        return exitcode, ""


def _decode_label(label: str | bytes) -> str:
    """Return a widget label as `str`, decoding it if urwid returned raw bytes."""
    return label if isinstance(label, str) else label.decode()


class InputDialogDisplay(DialogDisplay):
    """Dialog with a single-line text entry field."""

    def __init__(self, text: _TagMarkup | None, height: int | str, width: int | str) -> None:
        """Initialize with an empty single-line text entry field, focused."""
        self.edit = urwid.Edit()
        body = urwid.AttrMap(urwid.ListBox(urwid.SimpleListWalker([self.edit]), flow=True), "selectable", "focustext")

        super().__init__(text, height, width, body)

        self.set_focus_part("body")

    def unhandled_input(self, key: str | tuple[str, int, int, int]) -> bool | None:
        """Press the first button on :kbd:`enter`, which the entry field leaves unhandled.

        :raises DialogExit: on :kbd:`enter`, with the exit code of the first button.
        """
        if key != "enter" or self.default_exitcode is None:
            return None
        raise DialogExit(self.default_exitcode)

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """Return the exit code together with the entered text."""
        return exitcode, self.edit.get_edit_text()


class TextDialogDisplay(DialogDisplay):
    """Dialog that displays the contents of a file in a scrollable list box.

    The arrow and page keys scroll the file while the buttons have the focus.
    """

    frame_class = BodyScrollingPile

    def __init__(self, file: str, height: int | str, width: int | str) -> None:
        """Initialize with the contents of `file` loaded into the scrollable list box."""
        with open(file, encoding="utf-8") as f:
            lines = [urwid.Text(line.rstrip()) for line in f]
        # read the whole file (being slow, not lazy this time)

        body = urwid.AttrMap(urwid.ListBox(urwid.SimpleListWalker(lines), flow=True), "selectable", "focustext")

        super().__init__(None, height, width, body)


class ListDialogDisplay(DialogDisplay):
    """Dialog listing selectable items, built by `constr` for each `(tag, item, default)` triple."""

    def __init__(
        self,
        text: _TagMarkup | None,
        height: int | str,
        width: int | str,
        constr: typing.Callable[[str, bool], _ListItem],
        items: tuple[str, ...],
        has_default: bool,
    ) -> None:
        """Initialize with one item widget per `(tag, item, default)` triple in `items`, built via `constr`."""
        j: list[tuple[str, ...]] = []
        k: int
        tail: tuple[str, ...]
        if has_default:
            k, tail = 3, ()
        else:
            k, tail = 2, ("no",)
        while items:
            j.append(items[:k] + tail)
            items = items[k:]

        lines = []
        self.items: list[_ListItem] = []
        for tag, item, default in j:
            item_widget = constr(tag, default == "on")
            self.items.append(item_widget)
            w: urwid.Widget = urwid.Columns([(12, item_widget), urwid.Text(item)], 2)
            w = urwid.AttrMap(w, "selectable", "focus")
            lines.append(w)

        lb = urwid.AttrMap(urwid.ListBox(urwid.SimpleListWalker(lines), flow=True), "selectable")
        super().__init__(text, height, width, lb)

        self.set_focus_part("body")

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """Print the tag of the item selected."""
        if exitcode != 0:
            return exitcode, ""
        s = ""
        for i in self.items:
            if i.get_state():
                s = _decode_label(i.get_label())
                break
        return exitcode, s


class CheckListDialogDisplay(ListDialogDisplay):
    """Dialog listing checkbox items, mimicking dialog(1)'s ``--checklist``."""

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """Put each checked item in double quotes with a trailing space."""
        if exitcode != 0:
            return exitcode, ""
        labels = [_decode_label(i.get_label()) for i in self.items if i.get_state()]

        return exitcode, "".join(f'"{tag}" ' for tag in labels)


class MenuItem(urwid.Text):
    """A custom widget for the --menu option."""

    def __init__(self, label: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]) -> None:
        """Initialize unselected, with `label` as its text."""
        super().__init__(label, selectable=True)
        self.state = False

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Select this item and end the dialog on :kbd:`enter`, otherwise return the key unhandled.

        :raises DialogExit: when `key` is :kbd:`enter`, to end the dialog with this item selected.
        """
        if key == "enter":
            self.state = True
            raise DialogExit(0)
        return key

    def mouse_event(
        self,
        size: tuple[()] | tuple[int] | tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Select this item and end the dialog on a mouse release.

        :raises DialogExit: when `event` is a mouse release, to end the dialog with this item selected.
        """
        if event == "mouse release":
            self.state = True
            raise DialogExit(0)
        return False

    def get_state(self) -> bool:
        """Return whether this item has been selected."""
        return self.state

    def get_label(self) -> str:
        """Just alias to text."""
        return _decode_label(self.text)


def do_checklist(
    text: str,
    height: str,
    width: str,
    list_height: str,  # ignored, kept for a uniform do_* signature
    *items: str,
) -> CheckListDialogDisplay:
    """Build a checklist dialog for the ``--checklist`` command-line mode."""

    def constr(tag: str, state: bool) -> urwid.CheckBox:
        return urwid.CheckBox(tag, state)

    d = CheckListDialogDisplay(text, height, width, constr, items, True)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_inputbox(text: str, height: str, width: str) -> InputDialogDisplay:
    """Build an input dialog for the ``--inputbox`` command-line mode."""
    d = InputDialogDisplay(text, height, width)
    d.add_buttons([("Exit", 0)])
    return d


def do_menu(
    text: str,
    height: str,
    width: str,
    menu_height: str,  # ignored, kept for a uniform do_* signature
    *items: str,
) -> ListDialogDisplay:
    """Build a menu dialog for the ``--menu`` command-line mode."""

    def constr(tag: str, state: bool) -> MenuItem:  # state unused, kept for a uniform constr shape
        return MenuItem(tag)

    d = ListDialogDisplay(text, height, width, constr, items, False)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_msgbox(text: str, height: str, width: str) -> DialogDisplay:
    """Build a plain message dialog for the ``--msgbox`` command-line mode."""
    d = DialogDisplay(text, height, width)
    d.add_buttons([("OK", 0)])
    return d


def do_radiolist(
    text: str,
    height: str,
    width: str,
    list_height: str,  # ignored, kept for a uniform do_* signature
    *items: str,
) -> ListDialogDisplay:
    """Build a radio-button list dialog for the ``--radiolist`` command-line mode."""
    radiolist: list[urwid.RadioButton] = []

    def constr(  # pylint: disable=dangerous-default-value
        tag: str,
        state: bool,
        radiolist: list[urwid.RadioButton] = radiolist,
    ) -> urwid.RadioButton:
        return urwid.RadioButton(radiolist, tag, state)

    d = ListDialogDisplay(text, height, width, constr, items, True)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_textbox(file: str, height: str, width: str) -> TextDialogDisplay:
    """Build a dialog showing the contents of `file` for the ``--textbox`` command-line mode."""
    d = TextDialogDisplay(file, height, width)
    d.add_buttons([("Exit", 0)])
    return d


def do_yesno(text: str, height: str, width: str) -> DialogDisplay:
    """Build a yes/no dialog for the ``--yesno`` command-line mode."""
    d = DialogDisplay(text, height, width)
    d.add_buttons([("Yes", 0), ("No", 1)])
    return d


# pylint: disable-next=consider-using-namedtuple-or-dataclass  # made before argparse in stdlib
MODES: dict[str, tuple[typing.Callable[..., DialogDisplay], str]] = {
    "--checklist": (do_checklist, "text height width list-height [ tag item status ] ..."),
    "--inputbox": (do_inputbox, "text height width"),
    "--menu": (do_menu, "text height width menu-height [ tag item ] ..."),
    "--msgbox": (do_msgbox, "text height width"),
    "--radiolist": (do_radiolist, "text height width list-height [ tag item status ] ..."),
    "--textbox": (do_textbox, "file height width"),
    "--yesno": (do_yesno, "text height width"),
}


def show_usage() -> None:
    """Display a helpful usage message."""
    modelist = sorted((mode, help_mode) for (mode, (fn, help_mode)) in MODES.items())

    sys.stdout.write(
        (__doc__ or "")  # noqa: FURB143  # __doc__ is None under python -OO
        + "\n".join([f"{mode:<15} {help_mode}" for (mode, help_mode) in modelist])
        + """

height and width may be set to 0 to auto-size.
list-height and menu-height are currently ignored.
status may be either on or off.
"""
    )


def main() -> None:
    """Parse the command line, run the requested dialog mode, and exit with its exit code."""
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        show_usage()
        return

    # Create a DialogDisplay instance
    fn, _help_mode = MODES[sys.argv[1]]
    d = fn(*sys.argv[2:])

    # Run it
    exitcode, exitstring = d.main()

    # Exit
    if exitstring:
        sys.stderr.write(f"{exitstring}\n")

    sys.exit(exitcode)


if __name__ == "__main__":
    main()
