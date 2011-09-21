#!/usr/bin/python

import urwid

class PopUpDialog(urwid.WidgetWrap):
    """A dialog that appears with nothing but a close button """
    signals = ['close']
    def __init__(self):
        close_button = urwid.Button("confirm")
        urwid.connect_signal(close_button, 'click',
            lambda button:self._emit("close"))
        pile = urwid.Pile([urwid.Text("this is a pop-up"), close_button])
        fill = urwid.Filler(pile)
        self.__super.__init__(urwid.AttrWrap(fill, 'popbg'))


class ThingWithAPopUp(urwid.WidgetWrap):
    def __init__(self):
        self.__super.__init__(urwid.Button("click-me"))
        urwid.connect_signal(self._w, 'click', self.open_pop_up)
        self._pop_up_dialog = None

    def open_pop_up(self, button):
        self._pop_up_dialog = PopUpDialog()
        urwid.connect_signal(self._pop_up_dialog, 'close', self.close_pop_up)
        self._invalidate()

    def close_pop_up(self, button):
        self._pop_up_dialog = None
        self._invalidate()

    def render(self, size, focus=False):
        canv = self.__super.render(size, focus)
        if self._pop_up_dialog:
            canv = urwid.CompositeCanvas(canv)
            canv.set_pop_up(
                self._pop_up_dialog, left=0, top=1,
                overlay_width=30, overlay_height=4)
        return canv


fill = urwid.Filler(urwid.Padding(ThingWithAPopUp(), 'center', 15))
loop = urwid.MainLoop(
    fill,
    [('popbg', 'white', 'dark blue')],
    pop_ups=True)
loop.run()

