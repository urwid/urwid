import operator
import unittest

import urwid


class PartialExtendTest(unittest.TestCase):
    def test_failed_iterator_reports_the_retained_prefix(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for prefix in ([], [2], [2, 3, 4]):
                with self.subTest(operation=operation, prefix=prefix):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))
                    failure = ValueError("Input failed")

                    def incoming():
                        yield from prefix
                        raise failure

                    with self.assertRaises(ValueError) as caught:
                        operation(items, incoming())

                    self.assertIs(caught.exception, failure)
                    self.assertEqual(items, [1, *prefix])
                    self.assertEqual(changes, [[1, *prefix]] if prefix else [])

    def test_interruption_reports_partial_changes(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for error_type in (KeyboardInterrupt, SystemExit, GeneratorExit):
                with self.subTest(operation=operation, error_type=error_type):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))
                    failure = error_type()

                    def incoming():
                        yield 2
                        raise failure

                    with self.assertRaises(error_type) as caught:
                        operation(items, incoming())

                    self.assertIs(caught.exception, failure)
                    self.assertEqual(changes, [[1, 2]])

    def test_successful_extension_notifies_once(self):
        for operation in (urwid.MonitoredList.extend, operator.iadd):
            for values in ([], [2, 3]):
                with self.subTest(operation=operation, values=values):
                    items = urwid.MonitoredList([1])
                    changes = []
                    items.set_modified_callback(lambda: changes.append(list(items)))

                    result = operation(items, iter(values))

                    if operation is operator.iadd:
                        self.assertIs(result, items)
                    else:
                        self.assertIsNone(result)
                    self.assertEqual(changes, [[1, *values]])

    def test_failure_to_start_iteration_does_not_notify(self):
        class BrokenIterable:
            def __iter__(self):
                raise ValueError("Cannot iterate")

        items = urwid.MonitoredList([1])
        changes = []
        items.set_modified_callback(lambda: changes.append(list(items)))

        with self.assertRaisesRegex(ValueError, "Cannot iterate"):
            items.extend(BrokenIterable())

        self.assertEqual(items, [1])
        self.assertEqual(changes, [])

    def test_simple_list_walker_emits_modified_for_partial_extension(self):
        first = urwid.Text("first")
        added = urwid.Text("added")
        walker = urwid.SimpleListWalker([first])
        changes = []
        urwid.connect_signal(walker, "modified", lambda: changes.append(list(walker)))

        def incoming():
            yield added
            raise ValueError("Input failed")

        with self.assertRaisesRegex(ValueError, "Input failed"):
            walker.extend(incoming())

        self.assertEqual(changes, [[first, added]])
        self.assertEqual(walker.focus, 0)

    def test_focus_list_still_validates_input_before_changing_contents(self):
        for operation in (urwid.MonitoredFocusList.extend, operator.iadd):
            with self.subTest(operation=operation):
                items = urwid.MonitoredFocusList([1], focus=0)
                changes = []
                items.set_modified_callback(lambda: changes.append(list(items)))

                def incoming():
                    yield 2
                    raise ValueError("Input failed")

                with self.assertRaisesRegex(ValueError, "Input failed"):
                    operation(items, incoming())

                self.assertEqual(items, [1])
                self.assertEqual(items.focus, 0)
                self.assertEqual(changes, [])
