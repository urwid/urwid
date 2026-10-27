from __future__ import annotations

import unittest

import urwid
import urwid.testing


class SelectableIconTest(unittest.TestCase):
    def test_cursor_and_render(self) -> None:
        icon = urwid.SelectableIcon("[!]", cursor_position=1)

        self.assertTrue(icon.selectable())
        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), icon.sizing())
        self.assertEqual((3, 1), icon.pack(()))
        self.assertIsNone(icon.render((4,)).cursor)
        self.assertEqual((1, 0), icon.render((4,), focus=True).cursor)
        self.assertEqual([b"[!] "], icon.render((4,), focus=True).text)
        self.assertEqual("left", icon.keypress((4,), "left"))

    def test_no_cursor(self) -> None:
        for name, position in (("none", None), ("past the text", 4)):
            with self.subTest(name):
                icon = urwid.SelectableIcon("[!]", cursor_position=position)

                self.assertTrue(icon.selectable())
                self.assertIsNone(icon.get_cursor_coords((4,)))
                self.assertIsNone(icon.render((4,), focus=True).cursor)
                self.assertIsNone(icon.render((), focus=True).cursor)
                self.assertEqual([b"[!] "], icon.render((4,), focus=True).text)


class ButtonTest(unittest.TestCase):
    def test_keyword_construction_and_pack(self) -> None:
        button = urwid.Button(label="label", align=urwid.CENTER)

        self.assertTrue(button.selectable())
        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), button.sizing())
        self.assertEqual("label", button.label)
        self.assertEqual((9, 1), button.pack())
        self.assertEqual((9, 1), button.pack(()))
        self.assertEqual([b"< label >"], button.render(()).text)

    def test_flow_align(self) -> None:
        centered = urwid.Button("label", align=urwid.CENTER)
        right = urwid.Button("label", align=urwid.RIGHT)

        self.assertEqual(["<  label  >"], [line.decode() for line in centered.render((11,)).text])
        self.assertEqual(["<   label >"], [line.decode() for line in right.render((11,)).text])

    def test_set_label(self) -> None:
        button = urwid.Button("Ok")
        button.set_label(("bright", "Yup"))

        self.assertEqual("Yup", button.label)
        self.assertEqual("Yup", button.get_label())
        self.assertEqual([b"< Yup >"], button.render(()).text)

    def test_on_press_user_data(self) -> None:
        received: list[tuple[str, object]] = []

        def on_press(btn: urwid.Button, user_data: object) -> None:
            received.append((btn.label, user_data))

        button = urwid.Button("Go", on_press=on_press, user_data="payload")

        self.assertIsNone(button.keypress((10,), "enter"))
        self.assertIsNone(button.keypress((10,), " "))
        self.assertEqual("left", button.keypress((10,), "left"))
        self.assertTrue(button.mouse_event((10,), "mouse press", 1, 1, 0, True))
        self.assertFalse(button.mouse_event((10,), "mouse press", 2, 1, 0, True))
        self.assertEqual([("Go", "payload"), ("Go", "payload"), ("Go", "payload")], received)

    def test_connect_click_signal(self) -> None:
        clicks: list[str] = []
        button = urwid.Button("Ok")
        urwid.connect_signal(button, "click", lambda btn: clicks.append(btn.label))

        button.keypress((8,), "enter")
        self.assertEqual(["Ok"], clicks)

    def test_squish(self):
        urwid.testing.check_flow_sizing(urwid.Button("hello"))

    def test_cursor_position(self) -> None:
        self.assertEqual((2, 0), urwid.Button("Ok").render((6,), focus=True).cursor)
        self.assertEqual((3, 0), urwid.Button("Ok", cursor_position=1).render((6,), focus=True).cursor)
        self.assertIsNone(urwid.Button("Ok", cursor_position=None).render((6,), focus=True).cursor)

    def test_brackets(self) -> None:
        for name, kwargs, expected in (
            ("default", {}, b"< Ok >"),
            ("wide", {"left": "[[", "right": "]]"}, b"[[ Ok ]]"),
            ("left only", {"left": "["}, b"[ Ok >"),
            ("no left", {"left": ""}, b"Ok >"),
            ("no right", {"right": ""}, b"< Ok"),
            ("none", {"left": "", "right": ""}, b"Ok"),
            ("markup", {"left": ("attr", "["), "right": ["", ("attr", "]")]}, b"[ Ok ]"),
        ):
            with self.subTest(name):
                button = urwid.Button("Ok", **kwargs)

                self.assertEqual((len(expected), 1), button.pack())
                self.assertEqual([expected], button.render(()).text)
                urwid.testing.check_flow_sizing(button)

    def test_bracket_markup_attributes(self) -> None:
        button = urwid.Button("Ok", left=("attr", "["), right="]")

        (row,) = button.render(()).content()

        self.assertEqual(("attr", None, b"["), row[0])
        self.assertEqual({None}, {attr for attr, _cs, _text in row[1:]})

    def test_brackets_left_out_keep_click(self) -> None:
        clicks: list[str] = []
        button = urwid.Button("Link", left="", right="", on_press=lambda btn: clicks.append(btn.label))

        self.assertTrue(button.mouse_event((4,), "mouse press", 1, 0, 0, True))
        self.assertIsNone(button.keypress((4,), "enter"))
        self.assertEqual(["Link", "Link"], clicks)

    def test_class_brackets_keep_layout(self) -> None:
        """A subclass that sets the class attributes keeps its brackets in width-1 columns at the same indexes."""

        class SquareButton(urwid.Button):
            button_left = urwid.Text("[")
            button_right = urwid.Text("]")

        button = SquareButton("Ok")
        contents = button._w.contents

        self.assertEqual([b"[ Ok ]"], button.render(()).text)
        self.assertIs(SquareButton.button_left, contents[0][0])
        self.assertIs(SquareButton.button_right, contents[2][0])
        self.assertEqual((urwid.GIVEN, 1, False), contents[0][1])
        self.assertEqual((urwid.GIVEN, 1, False), contents[2][1])


class CheckBoxTest(unittest.TestCase):
    def test_keyword_construction(self) -> None:
        checkbox = urwid.CheckBox(label="Confirm", state=True)

        self.assertTrue(checkbox.selectable())
        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), checkbox.sizing())
        self.assertEqual("Confirm", checkbox.label)
        self.assertIs(True, checkbox.state)
        self.assertEqual((11, 1), checkbox.pack())
        self.assertEqual([b"[X] Confirm"], checkbox.render(()).text)

    def test_toggle_and_mixed(self) -> None:
        checkbox = urwid.CheckBox("3-state", has_mixed=True)

        self.assertIs(False, checkbox.state)
        checkbox.toggle_state()
        self.assertIs(True, checkbox.state)
        checkbox.toggle_state()
        self.assertEqual("mixed", checkbox.state)
        checkbox.toggle_state()
        self.assertIs(False, checkbox.state)

    def test_on_state_change_and_postchange(self) -> None:
        changes: list[tuple[str, object, object]] = []

        def on_change(cb: urwid.CheckBox, new_state: bool, user_data: object) -> None:
            changes.append(("change", new_state, user_data))

        def on_post(cb: urwid.CheckBox, old_state: bool) -> None:
            changes.append(("postchange", old_state, cb.state))

        checkbox = urwid.CheckBox("box", state=False, on_state_change=on_change, user_data="ud")
        urwid.connect_signal(checkbox, "postchange", on_post)

        checkbox.state = True
        checkbox.set_state(False, do_callback=False)

        self.assertIs(False, checkbox.state)
        self.assertEqual([("change", True, "ud"), ("postchange", False, True)], changes)

    def test_checked_symbol_is_per_instance(self) -> None:
        marked = urwid.CheckBox("ok", state=True, checked_symbol="*")
        default = urwid.CheckBox("ok", state=True)

        self.assertIn(b"[*]", marked.render((10,)).text[0])
        self.assertIn(b"[X]", default.render((10,)).text[0])
        self.assertIs(urwid.CheckBox.states[True], default.states[True])

    def test_keypress_and_mouse(self) -> None:
        checkbox = urwid.CheckBox("press me")

        self.assertIsNone(checkbox.keypress((12,), " "))
        self.assertIs(True, checkbox.state)
        self.assertEqual("left", checkbox.keypress((12,), "left"))
        self.assertTrue(checkbox.mouse_event((12,), "mouse press", 1, 0, 0, True))
        self.assertIs(False, checkbox.state)

    def test_set_label(self) -> None:
        checkbox = urwid.CheckBox("foo")
        checkbox.set_label(("bright", "bar"))

        self.assertEqual("bar", checkbox.label)
        self.assertEqual("bar", checkbox.get_label())


class RadioButtonTest(unittest.TestCase):
    def test_group_and_first_true(self) -> None:
        group: list[urwid.RadioButton] = []
        first = urwid.RadioButton(group=group, label="Agree")
        second = urwid.RadioButton(group=group, label="Disagree", state=False)

        self.assertEqual([first, second], group)
        self.assertIs(True, first.state)
        self.assertIs(False, second.state)
        self.assertEqual([b"(X) Agree"], first.render(()).text)
        self.assertEqual([b"( ) Disagree"], second.render(()).text)

    def test_exclusive_selection(self) -> None:
        group: list[urwid.RadioButton] = []
        first = urwid.RadioButton(group, "A")
        second = urwid.RadioButton(group, "B")
        third = urwid.RadioButton(group, "C")

        second.toggle_state()
        self.assertEqual((False, True, False), (first.state, second.state, third.state))
        second.toggle_state()
        self.assertEqual((False, True, False), (first.state, second.state, third.state))
        third.state = True
        self.assertEqual((False, False, True), (first.state, second.state, third.state))

    def test_on_state_change(self) -> None:
        seen: list[tuple[str, bool]] = []
        group: list[urwid.RadioButton] = []
        urwid.RadioButton(group, "A")
        second = urwid.RadioButton(
            group,
            "B",
            on_state_change=lambda rb, state: seen.append((rb.label, state)),
        )

        second.set_state(True)
        self.assertEqual([("B", True)], seen)

    def test_signal_sequence(self) -> None:
        """Each button emits change and postchange once per transition, the selected one first."""
        events: list[tuple[str, str, object]] = []
        group: list[urwid.RadioButton] = []
        buttons = [urwid.RadioButton(group, label) for label in "ABC"]
        for button in buttons:
            urwid.connect_signal(button, "change", lambda rb, state: events.append(("change", rb.label, state)))
            urwid.connect_signal(button, "postchange", lambda rb, old: events.append(("post", rb.label, old)))

        buttons[1].set_state(True)
        buttons[2].state = True
        buttons[2].set_state(False)
        buttons[0].toggle_state()
        buttons[1].set_state(True, do_callback=False)

        self.assertEqual([False, True, False], [button.state for button in buttons])
        self.assertEqual(
            [
                ("change", "B", True),
                ("post", "B", False),
                ("change", "A", False),
                ("post", "A", True),
                ("change", "C", True),
                ("post", "C", False),
                ("change", "B", False),
                ("post", "B", True),
                ("change", "C", False),
                ("post", "C", True),
                ("change", "A", True),
                ("post", "A", False),
                ("change", "A", False),
                ("post", "A", True),
            ],
            events,
        )

    def test_reentrant_selection_leaves_one_selected(self) -> None:
        """A signal handler that moves the selection leaves exactly one button selected."""

        def select_on(
            signal: str,
            source: urwid.RadioButton,
            target: urwid.RadioButton,
            when: bool,
        ) -> None:
            # Fire only on the transition that `when` names, so a chain cannot loop.
            if signal == "change":
                urwid.connect_signal(source, signal, lambda rb, new: target.set_state(True) if new is when else None)
            else:
                urwid.connect_signal(
                    source, signal, lambda rb, old: target.set_state(True) if rb.state is when else None
                )

        # (description, handlers as (signal, source, target, fire when source becomes), expected states)
        cases = (
            ("postchange of the selected moves on", [("postchange", 1, 2, True)], [False, False, True, False]),
            ("change of the selected moves on", [("change", 1, 2, True)], [False, True, False, False]),
            ("postchange of a cleared one moves on", [("postchange", 0, 2, False)], [False, False, True, False]),
            (
                "postchange chain across three buttons",
                [("postchange", 1, 2, True), ("postchange", 2, 3, True)],
                [False, False, False, True],
            ),
            (
                "postchange of a cleared one starts a chain",
                [("postchange", 0, 2, False), ("postchange", 2, 3, True)],
                [False, False, False, True],
            ),
        )
        for description, handlers, expected in cases:
            with self.subTest(description):
                group: list[urwid.RadioButton] = []
                buttons = [urwid.RadioButton(group, label) for label in "ABCD"]
                for signal, source, target, when in handlers:
                    select_on(signal, buttons[source], buttons[target], when)

                buttons[1].set_state(True)

                self.assertEqual(expected, [button.state for button in buttons])

    def test_postchange_handler_unselecting_itself(self) -> None:
        """A button its own postchange handler unselects does not clear the previous selection."""
        group: list[urwid.RadioButton] = []
        first = urwid.RadioButton(group, "A")
        second = urwid.RadioButton(group, "B")
        urwid.connect_signal(second, "postchange", lambda rb, old: rb.set_state(False))

        second.set_state(True)

        self.assertEqual((True, False), (first.state, second.state))

    def test_squish(self):
        urwid.testing.check_flow_sizing(urwid.RadioButton([], "hello"))
