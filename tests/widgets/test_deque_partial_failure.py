from __future__ import annotations

import unittest

import urwid


class DequePartialFailureTest(unittest.TestCase):
    def test_partial_extension_propagates_notification_with_input_chained(self):
        for cls in [urwid.MonitoredDeque, urwid.SimpleDequeWalker]:
            for operation in ["extend", "extendleft", "__iadd__"]:
                for maxlen in [None, 2]:
                    for failure_type in [ValueError, KeyboardInterrupt, SystemExit, GeneratorExit]:
                        with self.subTest(cls=cls, operation=operation, maxlen=maxlen, failure_type=failure_type):
                            items = cls([1, 2], maxlen=maxlen)
                            failure = failure_type("input failed")
                            seen = []

                            callback_error = RuntimeError("notification failed")

                            def changed():
                                seen.append(list(items))
                                raise callback_error

                            if cls is urwid.MonitoredDeque:
                                items.set_modified_callback(changed)
                            else:
                                urwid.connect_signal(items, "modified", changed)

                            def incoming():
                                yield 3
                                raise failure

                            with self.assertRaises(BaseException) as caught:
                                getattr(items, operation)(incoming())
                            self.assertIs(callback_error, caught.exception)
                            self.assertIs(callback_error.__context__, failure)
                            expected = [3, 1, 2] if operation == "extendleft" else [1, 2, 3]
                            if maxlen is not None:
                                expected = expected[:maxlen] if operation == "extendleft" else expected[-maxlen:]
                            self.assertEqual(expected, list(items))
                            self.assertEqual([expected], seen)

    def test_callback_failures_propagate_with_input_failure_chained(self):
        for cls in [urwid.MonitoredDeque, urwid.SimpleDequeWalker]:
            for operation in ["extend", "extendleft", "__iadd__"]:
                for maxlen in [None, 2]:
                    for failure_type in [ValueError, KeyboardInterrupt, SystemExit, GeneratorExit]:
                        for shutdown_type in [RuntimeError, KeyboardInterrupt, SystemExit, GeneratorExit]:
                            with self.subTest(cls=cls, operation=operation, maxlen=maxlen,
                                              failure=failure_type, shutdown=shutdown_type):
                                items = cls([1, 2], maxlen=maxlen)
                                failure = failure_type("input failed")
                                shutdown = shutdown_type("callback requested shutdown")
                                seen = []

                                def changed():
                                    seen.append(list(items))
                                    raise shutdown

                                if cls is urwid.MonitoredDeque:
                                    items.set_modified_callback(changed)
                                else:
                                    urwid.connect_signal(items, "modified", changed)

                                def incoming():
                                    yield 3
                                    raise failure

                                with self.assertRaises(BaseException) as caught:
                                    getattr(items, operation)(incoming())
                                self.assertIs(caught.exception, shutdown)
                                self.assertIs(shutdown.__context__, failure)
                                expected = [3, 1, 2] if operation == "extendleft" else [1, 2, 3]
                                if maxlen is not None:
                                    expected = expected[:maxlen] if operation == "extendleft" else expected[-maxlen:]
                                self.assertEqual(expected, list(items))
                                self.assertEqual([expected], seen)

    def test_no_committed_change_does_not_notify(self):
        for cls in [urwid.MonitoredDeque, urwid.MonitoredFocusDeque,
                    urwid.SimpleDequeWalker, urwid.SimpleFocusDequeWalker]:
            for operation in ["extend", "extendleft", "__iadd__"]:
                for maxlen, yields in [(None, False), (0, True)]:
                    with self.subTest(cls=cls, operation=operation, maxlen=maxlen, yields=yields):
                        items = cls([1, 2], maxlen=maxlen)
                        original = list(items)
                        failure = ValueError("input failed")
                        seen = []
                        if cls in [urwid.MonitoredDeque, urwid.MonitoredFocusDeque]:
                            items.set_modified_callback(lambda: seen.append(True))
                        else:
                            urwid.connect_signal(items, "modified", lambda: seen.append(True))

                        def incoming():
                            if yields:
                                yield 3
                            raise failure

                        with self.assertRaises(ValueError) as caught:
                            getattr(items, operation)(incoming())
                        self.assertIs(failure, caught.exception)
                        self.assertEqual(original, list(items))
                        self.assertEqual([], seen)

    def test_focus_deque_materializes_failed_input_before_mutating(self):
        for cls in [urwid.MonitoredFocusDeque, urwid.SimpleFocusDequeWalker]:
            for operation in ["extend", "extendleft", "__iadd__"]:
                with self.subTest(cls=cls, operation=operation):
                    items = cls([1, 2], maxlen=2)
                    items.focus = 1
                    seen = []
                    if cls is urwid.MonitoredFocusDeque:
                        items.set_modified_callback(lambda: seen.append(True))
                    else:
                        urwid.connect_signal(items, "modified", lambda: seen.append(True))
                    failure = ValueError("input failed")

                    def incoming():
                        yield 3
                        raise failure

                    with self.assertRaises(ValueError) as caught:
                        getattr(items, operation)(incoming())
                    self.assertIs(failure, caught.exception)
                    self.assertEqual([1, 2], list(items))
                    self.assertEqual(1, items.focus)
                    self.assertEqual([], seen)

    def test_cached_deque_walker_redraw_after_partial_failure(self):
        for operation in ["extend", "extendleft", "__iadd__"]:
            for maxlen in [None, 2]:
                with self.subTest(operation=operation, maxlen=maxlen):
                    walker = urwid.SimpleDequeWalker([urwid.Text("old1"), urwid.Text("old2")], maxlen=maxlen)
                    box = urwid.ListBox(walker)
                    before = box.render((6, 3))
                    failure = ValueError("input failed")
                    seen = []

                    callback_error = RuntimeError("notification failed")

                    def changed():
                        seen.append(True)
                        raise callback_error

                    urwid.connect_signal(walker, "modified", changed)

                    def incoming():
                        yield urwid.Text("new")
                        raise failure

                    with self.assertRaises(BaseException) as caught:
                        getattr(walker, operation)(incoming())
                    self.assertIs(callback_error, caught.exception)
                    self.assertIs(callback_error.__context__, failure)
                    after = box.render((6, 3))
                    self.assertIsNot(before, after)
                    self.assertEqual(urwid.ListBox(walker).render((6, 3)).text, after.text)
                    self.assertEqual([True], seen)

    def test_successful_extension_still_propagates_notification_failure(self):
        for cls in [urwid.MonitoredDeque, urwid.SimpleDequeWalker]:
            for operation in ["extend", "extendleft", "__iadd__"]:
                with self.subTest(cls=cls, operation=operation):
                    items = cls([1, 2])
                    failure = RuntimeError("notification failed")

                    def changed():
                        raise failure

                    if cls is urwid.MonitoredDeque:
                        items.set_modified_callback(changed)
                    else:
                        urwid.connect_signal(items, "modified", changed)
                    with self.assertRaises(RuntimeError) as caught:
                        getattr(items, operation)([3])
                    self.assertIs(failure, caught.exception)
                    self.assertEqual([3, 1, 2] if operation == "extendleft" else [1, 2, 3], list(items))
