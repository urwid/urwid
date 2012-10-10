import urwid

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
        game.update_place(self)

class Thing(urwid.WidgetWrap):
    def __init__(self, name):
        super(Thing, self).__init__(
            ActionButton([u" * take ", name], self.take_thing))
        self.name = name

    def take_thing(self, button):
        self._w = urwid.Text(u" - %s (taken)" % self.name)
        game.take_thing(self)

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

class AdventureGame(object):
    def __init__(self):
        self.log = urwid.SimpleFocusListWalker([])
        self.top = urwid.ListBox(self.log)
        self.inventory = set()
        self.update_place(map_top)

    def update_place(self, place):
        if self.log: # disable interaction with previous place
            self.log[-1] = urwid.WidgetDisable(self.log[-1])
        self.log.append(urwid.Pile([place.heading] + place.choices))
        self.top.focus_position = len(self.log) - 1
        self.place = place

    def take_thing(self, thing):
        self.inventory.add(thing.name)
        if self.inventory >= set([u'sugar', u'lemon', u'jug']):
            response = urwid.Text(u'You can make lemonade!\n')
            done = ActionButton(u' - Joy', exit_program)
            self.log[:] = [response, done]
        else:
            self.update_place(self.place)

game = AdventureGame()
urwid.MainLoop(game.top, palette=[('reversed', 'standout', '')]).run()
