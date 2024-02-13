from __future__ import annotations

import typing

import urwid

palette = [("I say", "default,bold", "default", "bold")]
ask = urwid.Edit(("I say", "What is your name?\n"))
reply = urwid.Text("")
button_inst = urwid.Button("Exit")
div = urwid.Divider()
pile = urwid.Pile([ask, div, reply, div, button_inst])
top = urwid.Filler(pile, valign="top")


def on_ask_change(_edit: urwid.Edit, new_edit_text: str) -> None:
    reply.set_text(("I say", f"Nice to meet you, {new_edit_text}"))


def on_exit_clicked(_button: urwid.Button) -> typing.NoReturn:
    raise urwid.ExitMainLoop()


urwid.connect_signal(ask, "change", on_ask_change)
urwid.connect_signal(button_inst, "click", on_exit_clicked)

urwid.MainLoop(top, palette).run()
