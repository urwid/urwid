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

"""
Urwid example similar to dialog(1) program

"""

from __future__ import annotations

import sys
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Hashable


class DialogExit(Exception):
    pass


class DialogDisplay:
    palette: typing.ClassVar[list[tuple[str, str, str, ...]]] = [
        ("body", "black", "light gray", "standout"),
        ("border", "black", "dark blue"),
        ("shadow", "white", "black"),
        ("selectable", "black", "dark cyan"),
        ("focus", "white", "dark blue", "bold"),
        ("focustext", "light gray", "dark blue"),
    ]

    def __init__(self, text, height: int | str, width: int | str, body=None) -> None:
        width = int(width)
        if width <= 0:
            width = (urwid.RELATIVE, 80)
        height = int(height)
        if height <= 0:
            height = (urwid.RELATIVE, 80)

        self.body = body
        if body is None:
            # fill space with nothing
            body = urwid.Filler(urwid.Divider(), urwid.TOP)

        self.frame = urwid.Frame(body, focus_part="footer")
        if text is not None:
            self.frame.header = urwid.Pile([urwid.Text(text), urwid.Divider()])
        w = self.frame

        # pad area around listbox
        w = urwid.Padding(w, urwid.LEFT, left=2, right=2)
        w = urwid.Filler(w, urwid.TOP, urwid.RELATIVE_100, top=1, bottom=1)
        w = urwid.AttrMap(w, "body")

        # "shadow" effect
        w = urwid.Columns([w, (2, urwid.AttrMap(urwid.Filler(urwid.Text(("border", "  ")), urwid.TOP), "shadow"))])
        w = urwid.Frame(w, footer=urwid.AttrMap(urwid.Text(("border", "  ")), "shadow"))

        # outermost border area
        w = urwid.Padding(w, urwid.CENTER, width)
        w = urwid.Filler(w, urwid.MIDDLE, height)
        w = urwid.AttrMap(w, "border")

        self.view = w

    def add_buttons(self, buttons) -> None:
        lines = []
        for name, exitcode in buttons:
            b = urwid.Button(name, self.button_press)
            b.exitcode = exitcode
            b = urwid.AttrMap(b, "selectable", "focus")
            lines.append(b)
        self.buttons = urwid.GridFlow(lines, 10, 3, 1, urwid.CENTER)
        self.frame.footer = urwid.Pile([urwid.Divider(), self.buttons], focus_item=1)

    def button_press(self, button) -> typing.NoReturn:
        raise DialogExit(button.exitcode)

    def main(self) -> tuple[int, str]:
        self.loop = urwid.MainLoop(self.view, self.palette)
        try:
            self.loop.run()
        except DialogExit as e:
            return self.on_exit(e.args[0])

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        return exitcode, ""


class InputDialogDisplay(DialogDisplay):
    def __init__(self, text, height: int | str, width: int | str) -> None:
        self.edit = urwid.Edit()
        body = urwid.ListBox(urwid.SimpleListWalker([self.edit]))
        body = urwid.AttrMap(body, "selectable", "focustext")

        super().__init__(text, height, width, body)

        self.frame.focus_position = "body"

    def unhandled_key(self, size, k: str) -> None:
        if k in {"up", "page up"}:
            self.frame.focus_position = "body"
        if k in {"down", "page down"}:
            self.frame.focus_position = "footer"
        if k == "enter":
            # pass enter to the "ok" button
            self.frame.focus_position = "footer"
            self.view.keypress(size, k)

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        return exitcode, self.edit.get_edit_text()


class TextDialogDisplay(DialogDisplay):
    def __init__(self, file: str, height: int | str, width: int | str) -> None:
        with open(file, encoding="utf-8") as f:
            lines = [urwid.Text(line.rstrip()) for line in f]
        # read the whole file (being slow, not lazy this time)

        body = urwid.ListBox(urwid.SimpleListWalker(lines))
        body = urwid.AttrMap(body, "selectable", "focustext")

        super().__init__(None, height, width, body)

    def unhandled_key(self, size, k: str) -> None:
        if k in {"up", "page up", "down", "page down"}:
            self.frame.focus_position = "body"
            self.view.keypress(size, k)
            self.frame.focus_position = "footer"


class ListDialogDisplay(DialogDisplay):
    def __init__(
        self,
        text,
        height: int | str,
        width: int | str,
        constr,
        items,
        has_default: bool,
    ) -> None:
        j = []
        if has_default:
            k, tail = 3, ()
        else:
            k, tail = 2, ("no",)
        while items:
            j.append(items[:k] + tail)
            items = items[k:]

        lines = []
        self.items = []
        for tag, item, default in j:
            w = constr(tag, default == "on")
            self.items.append(w)
            w = urwid.Columns([(12, w), urwid.Text(item)], 2)
            w = urwid.AttrMap(w, "selectable", "focus")
            lines.append(w)

        lb = urwid.ListBox(urwid.SimpleListWalker(lines))
        lb = urwid.AttrMap(lb, "selectable")
        super().__init__(text, height, width, lb)

        self.frame.focus_position = "body"

    def unhandled_key(self, size, k: str) -> None:
        if k in {"up", "page up"}:
            self.frame.focus_position = "body"
        if k in {"down", "page down"}:
            self.frame.focus_position = "footer"
        if k == "enter":
            # pass enter to the "ok" button
            self.frame.focus_position = "footer"
            self.buttons.focus_position = 0
            self.view.keypress(size, k)

    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """Print the tag of the item selected."""
        if exitcode != 0:
            return exitcode, ""
        s = ""
        for i in self.items:
            if i.get_state():
                s = i.get_label()
                break
        return exitcode, s


class CheckListDialogDisplay(ListDialogDisplay):
    def on_exit(self, exitcode: int) -> tuple[int, str]:
        """
        Mimic dialog(1)'s --checklist exit.
        Put each checked item in double quotes with a trailing space.
        """
        if exitcode != 0:
            return exitcode, ""
        labels = [i.get_label() for i in self.items if i.get_state()]

        return exitcode, "".join(f'"{tag}" ' for tag in labels)


class MenuItem(urwid.Text):
    """A custom widget for the --menu option"""

    def __init__(self, label: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]]) -> None:
        super().__init__(label)
        self.state = False

    def selectable(self) -> bool:
        return True

    def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:
        if key == "enter":
            self.state = True
            raise DialogExit(0)
        return key

    def mouse_event(
        self,
        size: tuple[int] | tuple[()],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        if event == "mouse release":
            self.state = True
            raise DialogExit(0)
        return False

    def get_state(self) -> bool:
        return self.state

    def get_label(self) -> str:
        """Just alias to text."""
        return self.text


def do_checklist(
    text,
    height: int,
    width: int,
    list_height: int,
    *items,
) -> CheckListDialogDisplay:
    def constr(tag, state: bool) -> urwid.CheckBox:
        return urwid.CheckBox(tag, state)

    d = CheckListDialogDisplay(text, height, width, constr, items, True)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_inputbox(text, height: int, width: int) -> InputDialogDisplay:
    d = InputDialogDisplay(text, height, width)
    d.add_buttons([("Exit", 0)])
    return d


def do_menu(
    text,
    height: int,
    width: int,
    menu_height: int,
    *items,
) -> ListDialogDisplay:
    def constr(tag, state: bool) -> MenuItem:
        return MenuItem(tag)

    d = ListDialogDisplay(text, height, width, constr, items, False)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_msgbox(text, height: int, width: int) -> DialogDisplay:
    d = DialogDisplay(text, height, width)
    d.add_buttons([("OK", 0)])
    return d


def do_radiolist(
    text,
    height: int,
    width: int,
    list_height: int,
    *items,
) -> ListDialogDisplay:
    radiolist = []

    def constr(  # pylint: disable=dangerous-default-value
        tag,
        state: bool,
        radiolist: list[urwid.RadioButton] = radiolist,
    ) -> urwid.RadioButton:
        return urwid.RadioButton(radiolist, tag, state)

    d = ListDialogDisplay(text, height, width, constr, items, True)
    d.add_buttons([("OK", 0), ("Cancel", 1)])
    return d


def do_textbox(file: str, height: int, width: int) -> TextDialogDisplay:
    d = TextDialogDisplay(file, height, width)
    d.add_buttons([("Exit", 0)])
    return d


def do_yesno(text, height: int, width: int) -> DialogDisplay:
    d = DialogDisplay(text, height, width)
    d.add_buttons([("Yes", 0), ("No", 1)])
    return d


MODES = {  # pylint: disable=consider-using-namedtuple-or-dataclass  # made before argparse in stdlib
    "--checklist": (do_checklist, "text height width list-height [ tag item status ] ..."),
    "--inputbox": (do_inputbox, "text height width"),
    "--menu": (do_menu, "text height width menu-height [ tag item ] ..."),
    "--msgbox": (do_msgbox, "text height width"),
    "--radiolist": (do_radiolist, "text height width list-height [ tag item status ] ..."),
    "--textbox": (do_textbox, "file height width"),
    "--yesno": (do_yesno, "text height width"),
}


def show_usage():
    """
    Display a helpful usage message.
    """
    modelist = sorted((mode, help_mode) for (mode, (fn, help_mode)) in MODES.items())

    sys.stdout.write(
        __doc__
        + "\n".join([f"{mode:<15} {help_mode}" for (mode, help_mode) in modelist])
        + """

height and width may be set to 0 to auto-size.
list-height and menu-height are currently ignored.
status may be either on or off.
"""
    )


def main() -> None:
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
