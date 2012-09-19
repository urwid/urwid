import urwid

class MenuButton(urwid.Button):
    def __init__(self, caption, callback):
        super(MenuButton, self).__init__("")
        urwid.connect_signal(self, 'click', callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption, 0),
            None, focus_map='reversed')

class SubMenu(urwid.WidgetWrap):
    def __init__(self, caption, choices):
        super(SubMenu, self).__init__(
            MenuButton(u"MENU: %s" % caption, self.open_menu))
        self.menu = Menu(caption, choices)

    def open_menu(self, button):
        loop.widget = self.menu

class Menu(urwid.ListBox):
    def __init__(self, title, choices):
        super(Menu, self).__init__(urwid.SimpleListWalker([
            urwid.Text(title),
            urwid.Divider()]))
        self.body.extend(choices)
        self.title = title

class Choice(urwid.WidgetWrap):
    def __init__(self, caption):
        super(Choice, self).__init__(
            MenuButton(caption, self.item_chosen))
        self.caption = caption

    def item_chosen(self, button):
        response = urwid.Text(u'You chose %s' % self.caption)
        loop.widget = urwid.Filler(response)
        # exit on the next input from user
        loop.unhandled_input = exit_program

def exit_program(key):
    raise urwid.ExitMainLoop()

menu_top = Menu(u'Main Menu', [
    SubMenu(u'Applications', [
        SubMenu(u'Accessories', [
            Choice(u'Text Editor'),
            Choice(u'Terminal'),
        ]),
    ]),
    SubMenu(u'System', [
        SubMenu(u'Preferences', [
            Choice(u'Appearance'),
        ]),
        Choice(u'Lock Screen'),
    ]),
])

loop = urwid.MainLoop(menu_top,
    palette=[('reversed', 'standout', '')])
loop.run()
