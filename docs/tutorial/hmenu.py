from __future__ import annotations

import urwid


class MenuButton(urwid.Button):
    def __init__(self, caption, callback):
        super().__init__("")
        urwid.connect_signal(self, 'click', callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(
            ['  \N{BULLET} ', caption], 2), None, 'selected')

class SubMenu(urwid.WidgetWrap):
    def __init__(self, caption, choices):
        super().__init__(MenuButton(
            [caption, "\N{HORIZONTAL ELLIPSIS}"], self.open_menu))
        line = urwid.Divider('\N{LOWER ONE QUARTER BLOCK}')
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([
            urwid.AttrMap(urwid.Text(["\n  ", caption]), 'heading'),
            urwid.AttrMap(line, 'line'),
            urwid.Divider()] + choices + [urwid.Divider()]))
        self.menu = urwid.AttrMap(listbox, 'options')

    def open_menu(self, button):
        top.open_box(self.menu)

class Choice(urwid.WidgetWrap):
    def __init__(self, caption):
        super().__init__(
            MenuButton(caption, self.item_chosen))
        self.caption = caption

    def item_chosen(self, button):
        response = urwid.Text(['  You chose ', self.caption, '\n'])
        done = MenuButton('Ok', exit_program)
        response_box = urwid.Filler(urwid.Pile([response, done]))
        top.open_box(urwid.AttrMap(response_box, 'options'))

def exit_program(key):
    raise urwid.ExitMainLoop()

menu_top = SubMenu('Main Menu', [
    SubMenu('Applications', [
        SubMenu('Accessories', [
            Choice('Text Editor'),
            Choice('Terminal'),
        ]),
    ]),
    SubMenu('System', [
        SubMenu('Preferences', [
            Choice('Appearance'),
        ]),
        Choice('Lock Screen'),
    ]),
])

palette = [
    (None,  'light gray', 'black'),
    ('heading', 'black', 'light gray'),
    ('line', 'black', 'light gray'),
    ('options', 'dark gray', 'black'),
    ('focus heading', 'white', 'dark red'),
    ('focus line', 'black', 'dark red'),
    ('focus options', 'black', 'light gray'),
    ('selected', 'white', 'dark blue')]
focus_map = {
    'heading': 'focus heading',
    'options': 'focus options',
    'line': 'focus line'}

class HorizontalBoxes(urwid.Columns):
    def __init__(self):
        super().__init__([], dividechars=1)

    def open_box(self, box):
        if self.contents:
            del self.contents[self.focus_position + 1:]
        self.contents.append((urwid.AttrMap(box, 'options', focus_map),
            self.options('given', 24)))
        self.focus_position = len(self.contents) - 1

top = HorizontalBoxes()
top.open_box(menu_top.menu)
urwid.MainLoop(urwid.Filler(top, 'middle', 10), palette).run()
