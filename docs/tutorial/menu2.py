import urwid

def menu_button(caption, callback):
    button = urwid.Button(caption)
    urwid.connect_signal(button, 'click', callback)
    return urwid.AttrMap(button, None, focus_map='reversed')

def sub_menu(caption, choices):
    contents = menu(caption, choices)
    def open_menu(button):
        return top.open_menu(contents)
    return menu_button(u'MENU: %s' % caption, open_menu)

def menu(title, choices):
    body = [urwid.Text(title), urwid.Divider()]
    body.extend(choices)
    return urwid.ListBox(urwid.SimpleFocusListWalker(body))

def item_chosen(button):
    response = urwid.Text(u'You chose %s' % button.label)
    top.open_menu(urwid.Filler(response))
    # exit on the next input from user
    loop.unhandled_input = exit_program

def exit_program(key):
    raise urwid.ExitMainLoop()

menu_top = menu(u'Main Menu', [
    sub_menu(u'Applications', [
        sub_menu(u'Accessories', [
            menu_button(u'Text Editor', item_chosen),
            menu_button(u'Terminal', item_chosen),
        ]),
    ]),
    sub_menu(u'System', [
        sub_menu(u'Preferences', [
            menu_button(u'Appearance', item_chosen),
        ]),
        menu_button(u'Lock Screen', item_chosen),
    ]),
])

class NestedMenus(urwid.WidgetPlaceholder):
    def __init__(self, menu):
        super(NestedMenus, self).__init__(urwid.SolidFill(u'/'))
        self.menu_level = 0
        self.open_menu(menu)

    def open_menu(self, menu):
        self.original_widget = urwid.Overlay(urwid.LineBox(menu),
            self.original_widget, 'left', 24, 'top', 8,
            left=self.menu_level * 2, top=self.menu_level * 2)
        self.menu_level += 1

top = NestedMenus(menu_top)
loop = urwid.MainLoop(top, palette=[('reversed', 'standout', '')])
loop.run()
