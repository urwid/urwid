from __future__ import annotations

import unittest

import urwid


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
