import unittest
import doctest

from .. import (widget, wimp, decoration, display_common, main_loop,
                monitored_list, raw_display, split_repr, util, signals)


def load_tests(loader, tests, ignore):
    module_doctests = [
        widget,
        wimp,
        decoration,
        display_common,
        main_loop,
        monitored_list,
        raw_display,
        split_repr,
        util,
        signals,
        ]
    for m in module_doctests:
        tests.addTests(doctest.DocTestSuite(m,
            optionflags=doctest.ELLIPSIS | doctest.IGNORE_EXCEPTION_DETAIL))
    return tests
