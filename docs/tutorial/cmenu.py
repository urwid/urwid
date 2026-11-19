from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable


def menu_button(
    caption: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
    callback: Callable[[urwid.Button], typing.Any],
) -> urwid.AttrMap:
    button = urwid.Button(caption, on_press=callback)
    return urwid.AttrMap(button, None, focus_map="reversed")


def sub_menu(
    caption: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
    choices: Iterable[urwid.Widget],
) -> urwid.Widget:
    contents = menu(caption, choices)

    def open_menu(button: urwid.Button) -> None:
        return open_box(contents)

    return menu_button([caption, "..."], open_menu)


def menu(
    title: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
    choices: Iterable[urwid.Widget],
) -> urwid.ListBox:
    body = [urwid.Text(title), urwid.Divider(), *choices]
    return urwid.ListBox(urwid.SimpleFocusListWalker(body))


def item_chosen(button: urwid.Button) -> None:
    response = urwid.Text(["You chose ", button.label, "\n"])
    done = menu_button("Ok", exit_program)
    open_box(urwid.Filler(urwid.Pile([response, done])))


def exit_program(button: urwid.Button) -> typing.NoReturn:
    raise urwid.ExitMainLoop


menu_top = menu(
    "Main Menu",
    [
        sub_menu(
            "Applications",
            [
                sub_menu(
                    "Accessories",
                    [
                        menu_button("Text Editor", item_chosen),
                        menu_button("Terminal", item_chosen),
                    ],
                ),
            ],
        ),
        sub_menu(
            "System",
            [
                sub_menu(
                    "Preferences",
                    [menu_button("Appearance", item_chosen)],
                ),
                menu_button("Lock Screen", item_chosen),
            ],
        ),
    ],
)


MAX_BOX_LEVELS = 4


def open_box(box: urwid.Widget) -> None:
    level = top.depth
    top.open(
        urwid.LineBox(box),
        width=(urwid.RELATIVE, 80),
        height=(urwid.RELATIVE, 80),
        min_width=24,
        min_height=8,
        left=level * 3,
        right=(MAX_BOX_LEVELS - level - 1) * 3,
        top=level * 2,
        bottom=(MAX_BOX_LEVELS - level - 1) * 2,
        close_on_menu=level > 0,
        close_on_click_outside=level > 0,
    )


top = urwid.OverlayStack(urwid.SolidFill("/"))
open_box(menu_top)
urwid.MainLoop(top, palette=[("reversed", "standout", "")]).run()
