import unittest
import doctest

import urwid
import urwid.numedit

def load_tests(loader, tests, ignore):
    module_doctests = [
        urwid.widget,
        urwid.wimp,
        urwid.decoration,
        urwid.display_common,
        urwid.main_loop,
        urwid.numedit,
        urwid.monitored_list,
        urwid.raw_display,
        'urwid.split_repr', # override function with same name
        urwid.util,
        urwid.signals,
        urwid.graphics,
        ]
    for m in module_doctests:
        tests.addTests(doctest.DocTestSuite(m,
            optionflags=doctest.ELLIPSIS | doctest.IGNORE_EXCEPTION_DETAIL))
    return tests
