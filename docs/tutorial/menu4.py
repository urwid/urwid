import urwid

inventory = set()

class MenuButton(urwid.Button):
    def __init__(self, caption, callback):
        super(MenuButton, self).__init__("")
        urwid.connect_signal(self, 'click', callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption, 1),
            None, focus_map='reversed')

class SubMenu(urwid.WidgetWrap):
    def __init__(self, caption, choices):
        super(SubMenu, self).__init__(
            MenuButton(u" > go to " + caption, self.open_menu))
        self.menu = Menu(caption, choices)
        # create links back to ourself
        for child in choices:
            child_menu = getattr(child, 'menu', None)
            if child_menu:
                child_menu.set_parent(self)

    def open_menu(self, button):
        loop.widget = self.menu

class Menu(urwid.ListBox):
    def __init__(self, title, choices):
        super(Menu, self).__init__(urwid.SimpleListWalker([
            urwid.Text(u"Location: " + title),
            urwid.Divider()]))
        self.body.extend(choices)
        self.title = title

    def set_parent(self, sub_menu):
        self.body[2:2] = [sub_menu]

class Thing(urwid.WidgetWrap):
    def __init__(self, name):
        super(Thing, self).__init__(
            MenuButton(u" * take " + name, self.take_thing))
        self.name = name

    def take_thing(self, button):
        self._w = urwid.Text(u" - %s (taken)" % self.name)
        inventory.add(self.name)
        if inventory >= set([u'sugar', u'lemon', u'jug']):
            response = urwid.Text(u'You can make lemonade!')
            loop.widget = urwid.Filler(response)
            # exit on the next input from user
            loop.unhandled_input = exit_program
            return
        loop.process_input(["up"]) # move focus off this widget

def exit_program(key):
    raise urwid.ExitMainLoop()

menu_top_sub = SubMenu(u'porch', [
    SubMenu(u'kitchen', [
        SubMenu(u'refrigerator', []),
        SubMenu(u'cupboard', [
            Thing(u'jug'),
        ]),
    ]),
    SubMenu(u'garden', [
        SubMenu(u'tree', [
            Thing(u'lemon'),
            Thing(u'bird'),
        ]),
    ]),
    SubMenu(u'street', [
        SubMenu(u'store', [
            Thing(u'sugar'),
        ]),
        SubMenu(u'lake', [
            SubMenu(u'beach', []),
        ]),
    ]),
])

loop = urwid.MainLoop(menu_top_sub.menu,
    palette=[('reversed', 'standout', '')])
loop.run()
