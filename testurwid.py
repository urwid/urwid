import urwid
from contextlib import contextmanager

from urwid import raw_display, curses_display

@contextmanager
def sstarter(module):
    try:
        s=module.Screen()
        s.start()
        yield s
    finally:
        s.stop()

def inputtest():
    input = []
    with sstarter(raw_display) as s:
        input.append(s.get_input())
    with sstarter(curses_display) as s:
        input.append(s.get_input())

    for s in input:
        print repr(s)
        print s

if __name__ == '__main__':
    inputtest()