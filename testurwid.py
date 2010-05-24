# coding: UTF-8

import urwid
from contextlib import contextmanager

from urwid import raw_display, curses_display
from urwid import Text

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

def widgettest():
    txt = urwid.Text(u"Hello World")
    txt2 = urwid.Text(u"A Second Line with ü")
    moretxt = [txt, txt2]
    for i in range(80):
        newtxt = urwid.Text(u"%d - Another Line with ü" % (i+2))
        moretxt.append(newtxt)
    moretxt.append(urwid.Edit("Edit box:"))
    lst = urwid.ListBox(moretxt)
    fill = urwid.Frame(lst)

    def show_or_exit(input):
        if input in ('q', 'Q'):
            raise urwid.ExitMainLoop()
    
    loop = urwid.MainLoop(fill, unhandled_input=show_or_exit)
    loop.run()

if __name__ == '__main__':
    #inputtest()
    widgettest()