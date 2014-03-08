import unittest
import doctest

import urwid

def load_tests(loader, tests, ignore):
    module_doctests = [
        'urwid.widget',
        'urwid.wimp',
        'urwid.decoration',
        'urwid.display_common',
        'urwid.main_loop',
        'urwid.monitored_list',
        'urwid.raw_display',
        'urwid.split_repr',
        'urwid.util',
        'urwid.signals',
        ]
    for m in module_doctests:
        tests.addTests(doctest.DocTestSuite(m,
            optionflags=doctest.ELLIPSIS | doctest.IGNORE_EXCEPTION_DETAIL))
    return tests
