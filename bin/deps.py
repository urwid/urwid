#!/usr/bin/env python
"""
show optional Urwid dependencies installed
"""
deps = []

try:
    import gi.repository
    deps.append("pygobject")
except ImportError:
    pass

try:
    import tornado
    deps.append("tornado")
except ImportError:
    pass

try:
    import trio
    deps.append("trio")
except ImportError:
    pass

try:
    import twisted
    deps.append("twisted")
except ImportError:
    pass

print(" ".join(deps))
