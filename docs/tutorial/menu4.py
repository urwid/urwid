import urwid

inventory = set()

class ActionButton(urwid.Button):
    def __init__(self, caption, callback):
        super(ActionButton, self).__init__("")
        urwid.connect_signal(self, 'click', callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption, 1),
            None, focus_map='reversed')

class Place(urwid.WidgetWrap):
    def __init__(self, name, choices):
        super(Place, self).__init__(
            ActionButton([u" > go to ", name], self.enter_place))
        self.heading = urwid.Text([u"\nLocation: ", name, "\n"])
        self.choices = choices
        # create links back to ourself
        for child in choices:
            getattr(child, 'choices', []).insert(0, self)

    def enter_place(self, button):
        top.move_to(self)

class Thing(urwid.WidgetWrap):
    def __init__(self, name):
        super(Thing, self).__init__(
            ActionButton([u" * take ", name], self.take_thing))
        self.name = name

    def take_thing(self, button):
        loop.process_input(["up"]) # move focus off this widget
        self._w = urwid.Text(u" - %s (taken)" % self.name)
        inventory.add(self.name)
        if inventory >= set([u'sugar', u'lemon', u'jug']):
            response = urwid.Text(u'You can make lemonade!\n')
            done = ActionButton(u' - Joy', exit_program)
            loop.widget = urwid.Filler(urwid.Pile([response, done]))

def exit_program(button):
    raise urwid.ExitMainLoop()

map_top = Place(u'porch', [
    Place(u'kitchen', [
        Place(u'refrigerator', []),
        Place(u'cupboard', [
            Thing(u'jug'),
        ]),
    ]),
    Place(u'garden', [
        Place(u'tree', [
            Thing(u'lemon'),
            Thing(u'bird'),
        ]),
    ]),
    Place(u'street', [
        Place(u'store', [
            Thing(u'sugar'),
        ]),
        Place(u'lake', [
            Place(u'beach', []),
        ]),
    ]),
])

class AdventureLog(urwid.ListBox):
    def __init__(self):
        log = urwid.SimpleFocusListWalker([])
        super(AdventureLog, self).__init__(log)

    def move_to(self, place):
        self.body.append(urwid.Pile([place.heading] + place.choices))
        self.focus_position = len(self.body) - 1

top = AdventureLog()
top.move_to(map_top)
loop = urwid.MainLoop(top, palette=[('reversed', 'standout', '')])
loop.run()
