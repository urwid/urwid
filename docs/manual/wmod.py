from __future__ import annotations

import urwid


class QuestionnaireItem(urwid.WidgetWrap):
    def __init__(self):
        self.options = []
        unsure = urwid.RadioButton(self.options, "Unsure")
        yes = urwid.RadioButton(self.options, "Yes")
        no = urwid.RadioButton(self.options, "No")
        display_widget = urwid.GridFlow([unsure, yes, no], 15, 3, 1, 'left')
        urwid.WidgetWrap.__init__(self, display_widget)

    def get_state(self):
        for o in self.options:
            if o.get_state() is True:
                return o.get_label()
