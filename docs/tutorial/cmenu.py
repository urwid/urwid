from __future__ import annotations

import urwid


def menu_button(caption, callback):
    button = urwid.Button(caption)
    urwid.connect_signal(button, 'click', callback)
    return urwid.AttrMap(button, None, focus_map='reversed')

def sub_menu(caption, choices):
    contents = menu(caption, choices)
    def open_menu(button):
        return top.open_box(contents)
    return menu_button([caption, '...'], open_menu)

def menu(title, choices):
    body = [urwid.Text(title), urwid.Divider()]
    body.extend(choices)
    return urwid.ListBox(urwid.SimpleFocusListWalker(body))

def item_chosen(button):
    response = urwid.Text(['You chose ', button.label, '\n'])
    done = menu_button('Ok', exit_program)
    top.open_box(urwid.Filler(urwid.Pile([response, done])))

def exit_program(button):
    raise urwid.ExitMainLoop()

menu_top = menu('Main Menu', [
    sub_menu('Applications', [
        sub_menu('Accessories', [
            menu_button('Text Editor', item_chosen),
            menu_button('Terminal', item_chosen),
        ]),
    ]),
    sub_menu('System', [
        sub_menu('Preferences', [
            menu_button('Appearance', item_chosen),
        ]),
        menu_button('Lock Screen', item_chosen),
    ]),
])

class CascadingBoxes(urwid.WidgetPlaceholder):
    max_box_levels = 4

    def __init__(self, box):
        super().__init__(urwid.SolidFill('/'))
        self.box_level = 0
        self.open_box(box)

    def open_box(self, box):
        self.original_widget = urwid.Overlay(urwid.LineBox(box),
            self.original_widget,
            align='center', width=(urwid.WHSettings.RELATIVE, 80),
            valign='middle', height=(urwid.WHSettings.RELATIVE, 80),
            min_width=24, min_height=8,
            left=self.box_level * 3,
            right=(self.max_box_levels - self.box_level - 1) * 3,
            top=self.box_level * 2,
            bottom=(self.max_box_levels - self.box_level - 1) * 2)
        self.box_level += 1

    def keypress(self, size, key):
        if key == 'esc' and self.box_level > 1:
            self.original_widget = self.original_widget[0]
            self.box_level -= 1
        else:
            return super().keypress(size, key)

top = CascadingBoxes(menu_top)
urwid.MainLoop(top, palette=[('reversed', 'standout', '')]).run()
