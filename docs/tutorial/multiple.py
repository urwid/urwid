from __future__ import annotations

import urwid


def question():
    return urwid.Pile([urwid.Edit(("I say", "What is your name?\n"))])


def answer(name):
    return urwid.Text(("I say", f"Nice to meet you, {name}\n"))


class ConversationListBox(urwid.ListBox):
    def __init__(self) -> None:
        body = urwid.SimpleFocusListWalker([question()])
        super().__init__(body)

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        key = super().keypress(size, key)
        if key != "enter":
            return key
        name = self.focus[0].edit_text
        if not name:
            raise urwid.ExitMainLoop()
        # replace or add response
        self.focus.contents[1:] = [(answer(name), self.focus.options())]
        pos = self.focus_position
        # add a new question
        self.body.insert(pos + 1, question())
        self.focus_position = pos + 1
        return None


palette = [("I say", "default,bold", "default")]
urwid.MainLoop(ConversationListBox(), palette).run()
