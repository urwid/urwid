#!/usr/bin/python

import urwid

class PopUpConfirm(urwid.WidgetWrap):
    def __init__(self):
        self.__super.__init__(urwid.Button("click-me"))
        def on_click(button):
            self._open_pop_up = True
            self._invalidate()
        urwid.connect_signal(self._w, 'click', on_click)
        self._open_pop_up = False
        self._pop_up_window = self._create_pop_up()

    def _create_pop_up(self):
        close_button = urwid.Button("confirm")
        def on_click(button):
            button.do_close()
            self._open_pop_up = False
        def set_close(fn):
            close_button.do_close = fn
        urwid.connect_signal(close_button, 'click', on_click)
        pile = urwid.Pile([urwid.Text("this is a pop-up"), close_button])
        fill = urwid.Filler(pile)
        amap = urwid.AttrWrap(fill, 'popbg')
        return (30, 4, amap, set_close)

    def render(self, size, focus=False):
        canv = self.__super.render(size, focus)
        if self._open_pop_up:
            canv = urwid.CompositeCanvas(canv)
            # same left column, one line below ourselves
            canv.coords['pop_up'] = (0, 1, self._pop_up_window)
        return canv


fill = urwid.Filler(urwid.Padding(PopUpConfirm(), 'center', 15))
loop = urwid.MainLoop(
    fill,
    [('popbg', 'white', 'dark blue')],
    pop_ups=True)
loop.run()

