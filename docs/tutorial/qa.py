from __future__ import annotations

import urwid


def exit_on_q(key: str) -> None:
    if key in {"q", "Q"}:
        raise urwid.ExitMainLoop()


class QuestionBox(urwid.Filler):
    def keypress(self, size, key: str) -> str | None:
        if key != "enter":
            return super().keypress(size, key)
        self.original_widget = urwid.Text(
            f"Nice to meet you,\n{edit.edit_text}.\n\nPress Q to exit.",
        )
        return None


edit = urwid.Edit("What is your name?\n")
fill = QuestionBox(edit)
loop = urwid.MainLoop(fill, unhandled_input=exit_on_q)
loop.run()
