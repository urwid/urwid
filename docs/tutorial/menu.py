import urwid

inventory = set()

class MenuButton(urwid.Button):
    def __init__(self, text, callback):
        super(MenuButton, self).__init__("", callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(text, 1),
            None, focus_map='reversed')

class SubMenu(urwid.WidgetWrap):
    def __init__(self, title, menu):
        super(SubMenu, self).__init__(
            MenuButton(u" > go to " + title, self.pressed))
        self.menu = menu

    def pressed(self, button):
        loop.widget = self.menu

class Thing(urwid.WidgetWrap):
    def __init__(self, name):
        super(Thing, self).__init__(
            MenuButton(u" * take " + name, self.pressed))
        self.name = name

    def pressed(self, button):
        self._w = urwid.Text(u" - " + self.name + " (taken)")
        inventory.add(self.name)
        if inventory >= set([u'sugar', u'lemon', u'jug']):
            raise urwid.ExitMainLoop()
        loop.process_input(["up"]) # move focus off this widget

class Menu(urwid.ListBox):
    def __init__(self, title, children):
        super(Menu, self).__init__(urwid.SimpleListWalker([
            urwid.Text(u"Location: " + title),
            urwid.Divider()] + list(children)))
        self.title = title

    def set_parent(self, sub_menu):
        self.body[2:2] = [sub_menu]

def menu(title, *contents):
    """Create menus and links back to parent menus"""
    menu_full = Menu(title, contents)
    sub_menu = SubMenu(title, menu_full)
    for child in contents:
        child_menu = getattr(child, 'menu', None)
        if child_menu:
            child_menu.set_parent(sub_menu)
    return sub_menu

menu_top = menu(u'porch',
    menu(u'kitchen',
        menu(u'refrigerator'),
        menu(u'cupboard',
            Thing(u'jug'),
        ),
    ),
    menu(u'garden',
        menu(u'tree',
            Thing(u'lemon'),
            Thing(u'bird'),
        ),
    ),
    menu(u'street',
        menu(u'store',
            Thing(u'sugar'),
            ),
        menu(u'lake',
            menu(u'beach'),
            ),
        ),
    )

loop = urwid.MainLoop(menu_top.menu,
    palette=[('reversed', 'standout', '')])
loop.run()
print u"Congratulations, you can make lemonade!"
