from __future__ import annotations

import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, MutableSequence


class ActionButton(urwid.Button):
    def __init__(
        self,
        caption: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
        callback: Callable[[ActionButton], typing.Any],
    ) -> None:
        super().__init__("", on_press=callback)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption, 1), None, focus_map="reversed")


class Place(urwid.WidgetWrap[ActionButton]):
    def __init__(self, name: str, choices: MutableSequence[urwid.Widget]) -> None:
        super().__init__(ActionButton([" > go to ", name], self.enter_place))
        self.heading = urwid.Text(["\nLocation: ", name, "\n"])
        self.choices = choices
        # create links back to ourself
        for child in choices:
            getattr(child, "choices", []).insert(0, self)

    def enter_place(self, button: ActionButton) -> None:
        game.update_place(self)


class Thing(urwid.WidgetWrap[ActionButton]):
    def __init__(self, name: str) -> None:
        super().__init__(ActionButton([" * take ", name], self.take_thing))
        self.name = name

    def take_thing(self, button: ActionButton) -> None:
        self._w = urwid.Text(f" - {self.name} (taken)")
        game.take_thing(self)


def exit_program(button: ActionButton) -> typing.NoReturn:
    raise urwid.ExitMainLoop()


map_top = Place(
    "porch",
    [
        Place(
            "kitchen",
            [
                Place("refrigerator", []),
                Place("cupboard", [Thing("jug")]),
            ],
        ),
        Place(
            "garden",
            [
                Place(
                    "tree",
                    [
                        Thing("lemon"),
                        Thing("bird"),
                    ],
                ),
            ],
        ),
        Place(
            "street",
            [
                Place("store", [Thing("sugar")]),
                Place(
                    "lake",
                    [Place("beach", [])],
                ),
            ],
        ),
    ],
)


class AdventureGame:
    def __init__(self) -> None:
        self.log = urwid.SimpleFocusListWalker([])
        self.top = urwid.ListBox(self.log)
        self.inventory = set()
        self.update_place(map_top)

    def update_place(self, place: Place) -> None:
        if self.log:  # disable interaction with previous place
            self.log[-1] = urwid.WidgetDisable(self.log[-1])
        self.log.append(urwid.Pile([place.heading, *place.choices]))
        self.top.focus_position = len(self.log) - 1
        self.place = place

    def take_thing(self, thing: Thing) -> None:
        self.inventory.add(thing.name)
        if self.inventory >= {"sugar", "lemon", "jug"}:
            response = urwid.Text("You can make lemonade!\n")
            done = ActionButton(" - Joy", exit_program)
            self.log[:] = [response, done]
        else:
            self.update_place(self.place)


game = AdventureGame()
urwid.MainLoop(game.top, palette=[("reversed", "standout", "")]).run()
