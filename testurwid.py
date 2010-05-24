import urwid
from contextlib import contextmanager

from urwid import raw_display

@contextmanager
def sstarter():
    try:
        s=raw_display.Screen()
        s.start()
        yield s
    finally:
        s.stop()

with sstarter() as s:
    input = s.get_input()

for s in input:
    print repr(s)
    print s