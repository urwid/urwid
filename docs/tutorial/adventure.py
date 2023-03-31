from __future__ import annotations

import urwid


class ActionButton(urwid.Button):
    def __init__(self, caption, callback):
        super().__init__("")
        urwid.connect_signal(self, 'click', callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption, 1),
            None, focus_map='reversed')

class Place(urwid.WidgetWrap):
    def __init__(self, name, choices):
        super().__init__(
            ActionButton([" > go to ", name], self.enter_place))
        self.heading = urwid.Text(["\nLocation: ", name, "\n"])
        self.choices = choices
        # create links back to ourself
        for child in choices:
            getattr(child, 'choices', []).insert(0, self)

    def enter_place(self, button):
        game.update_place(self)

class Thing(urwid.WidgetWrap):
    def __init__(self, name):
        super().__init__(
            ActionButton([" * take ", name], self.take_thing))
        self.name = name

    def take_thing(self, button):
        self._w = urwid.Text(f" - {self.name} (taken)")
        game.take_thing(self)

def exit_program(button):
    raise urwid.ExitMainLoop()

map_top = Place('porch', [
    Place('kitchen', [
        Place('refrigerator', []),
        Place('cupboard', [
            Thing('jug'),
        ]),
    ]),
    Place('garden', [
        Place('tree', [
            Thing('lemon'),
            Thing('bird'),
        ]),
    ]),
    Place('street', [
        Place('store', [
            Thing('sugar'),
        ]),
        Place('lake', [
            Place('beach', []),
        ]),
    ]),
])

class AdventureGame:
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
        if self.inventory >= {'sugar', 'lemon', 'jug'}:
            response = urwid.Text('You can make lemonade!\n')
            done = ActionButton(' - Joy', exit_program)
            self.log[:] = [response, done]
        else:
            self.update_place(self.place)

game = AdventureGame()
urwid.MainLoop(game.top, palette=[('reversed', 'standout', '')]).run()
