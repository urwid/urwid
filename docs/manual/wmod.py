from __future__ import annotations

import urwid


class QuestionnaireItem(urwid.WidgetWrap[urwid.GridFlow]):
    def __init__(self) -> None:
        self.options: list[urwid.RadioButton] = []
        unsure = urwid.RadioButton(self.options, "Unsure")
        yes = urwid.RadioButton(self.options, "Yes")
        no = urwid.RadioButton(self.options, "No")
        display_widget = urwid.GridFlow([unsure, yes, no], 15, 3, 1, "left")
        super().__init__(display_widget)

    def get_state(self) -> str:
        return next(o.label for o in self.options if o.state is True)
