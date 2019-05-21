#!/usr/bin/env python
#
# Urwid example similar to dialog(1) program
#    Copyright (C) 2004-2009  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

"""
Urwid example similar to dialog(1) program

"""

import sys

import urwid


class DialogExit(Exception):
    pass


class DialogDisplay:
    palette = [
        ('body','black','light gray', 'standout'),
        ('border','black','dark blue'),
        ('shadow','white','black'),
        ('selectable','black', 'dark cyan'),
        ('focus','white','dark blue','bold'),
        ('focustext','light gray','dark blue'),
        ]

    def __init__(self, text, height, width, body=None):
        width = int(width)
        if width <= 0:
            width = ('relative', 80)
        height = int(height)
        if height <= 0:
            height = ('relative', 80)

        self.body = body
        if body is None:
            # fill space with nothing
            body = urwid.Filler(urwid.Divider(),'top')

        self.frame = urwid.Frame( body, focus_part='footer')
        if text is not None:
            self.frame.header = urwid.Pile( [urwid.Text(text),
                urwid.Divider()] )
        w = self.frame

        # pad area around listbox
        w = urwid.Padding(w, ('fixed left',2), ('fixed right',2))
        w = urwid.Filler(w, ('fixed top',1), ('fixed bottom',1))
        w = urwid.AttrWrap(w, 'body')

        # "shadow" effect
        w = urwid.Columns( [w,('fixed', 2, urwid.AttrWrap(
            urwid.Filler(urwid.Text(('border','  ')), "top")
            ,'shadow'))])
        w = urwid.Frame( w, footer =
            urwid.AttrWrap(urwid.Text(('border','  ')),'shadow'))

        # outermost border area
        w = urwid.Padding(w, 'center', width )
        w = urwid.Filler(w, 'middle', height )
        w = urwid.AttrWrap( w, 'border' )

        self.view = w


    def add_buttons(self, buttons):
        l = []
        for name, exitcode in buttons:
            b = urwid.Button( name, self.button_press )
            b.exitcode = exitcode
            b = urwid.AttrWrap( b, 'selectable','focus' )
            l.append( b )
        self.buttons = urwid.GridFlow(l, 10, 3, 1, 'center')
        self.frame.footer = urwid.Pile( [ urwid.Divider(),
            self.buttons ], focus_item = 1)

    def button_press(self, button):
        raise DialogExit(button.exitcode)

    def main(self):
        self.loop = urwid.MainLoop(self.view, self.palette)
        try:
            self.loop.run()
        except DialogExit as e:
            return self.on_exit( e.args[0] )

    def on_exit(self, exitcode):
        return exitcode, ""



class InputDialogDisplay(DialogDisplay):
    def __init__(self, text, height, width):
        self.edit = urwid.Edit()
        body = urwid.ListBox(urwid.SimpleListWalker([self.edit]))
        body = urwid.AttrWrap(body, 'selectable','focustext')

        DialogDisplay.__init__(self, text, height, width, body)

        self.frame.set_focus('body')

    def unhandled_key(self, size, k):
        if k in ('up','page up'):
            self.frame.set_focus('body')
        if k in ('down','page down'):
            self.frame.set_focus('footer')
        if k == 'enter':
            # pass enter to the "ok" button
            self.frame.set_focus('footer')
            self.view.keypress( size, k )

    def on_exit(self, exitcode):
        return exitcode, self.edit.get_edit_text()


class TextDialogDisplay(DialogDisplay):
    def __init__(self, file, height, width):
        l = []
        # read the whole file (being slow, not lazy this time)
        for line in open(file).readlines():
            l.append( urwid.Text( line.rstrip() ))
        body = urwid.ListBox(urwid.SimpleListWalker(l))
        body = urwid.AttrWrap(body, 'selectable','focustext')

        DialogDisplay.__init__(self, None, height, width, body)


    def unhandled_key(self, size, k):
        if k in ('up','page up','down','page down'):
            self.frame.set_focus('body')
            self.view.keypress( size, k )
            self.frame.set_focus('footer')


class ListDialogDisplay(DialogDisplay):
    def __init__(self, text, height, width, constr, items, has_default):
        j = []
        if has_default:
            k, tail = 3, ()
        else:
            k, tail = 2, ("no",)
        while items:
            j.append( items[:k] + tail )
            items = items[k:]

        l = []
        self.items = []
        for tag, item, default in j:
            w = constr( tag, default=="on" )
            self.items.append(w)
            w = urwid.Columns( [('fixed', 12, w),
                urwid.Text(item)], 2 )
            w = urwid.AttrWrap(w, 'selectable','focus')
            l.append(w)

        lb = urwid.ListBox(urwid.SimpleListWalker(l))
        lb = urwid.AttrWrap( lb, "selectable" )
        DialogDisplay.__init__(self, text, height, width, lb )

        self.frame.set_focus('body')

    def unhandled_key(self, size, k):
        if k in ('up','page up'):
            self.frame.set_focus('body')
        if k in ('down','page down'):
            self.frame.set_focus('footer')
        if k == 'enter':
            # pass enter to the "ok" button
            self.frame.set_focus('footer')
            self.buttons.set_focus(0)
            self.view.keypress( size, k )

    def on_exit(self, exitcode):
        """Print the tag of the item selected."""
        if exitcode != 0:
            return exitcode, ""
        s = ""
        for i in self.items:
            if i.get_state():
                s = i.get_label()
                break
        return exitcode, s




class CheckListDialogDisplay(ListDialogDisplay):
    def on_exit(self, exitcode):
        """
        Mimic dialog(1)'s --checklist exit.
        Put each checked item in double quotes with a trailing space.
        """
        if exitcode != 0:
            return exitcode, ""
        l = []
        for i in self.items:
            if i.get_state():
                l.append(i.get_label())
        return exitcode, "".join(['"'+tag+'" ' for tag in l])




class MenuItem(urwid.Text):
    """A custom widget for the --menu option"""
    def __init__(self, label):
        urwid.Text.__init__(self, label)
        self.state = False
    def selectable(self):
        return True
    def keypress(self,size,key):
        if key == "enter":
            self.state = True
            raise DialogExit(0)
        return key
    def mouse_event(self,size,event,button,col,row,focus):
        if event=='mouse release':
            self.state = True
            raise DialogExit(0)
        return False
    def get_state(self):
        return self.state
    def get_label(self):
        text, attr = self.get_text()
        return text


def do_checklist(text, height, width, list_height, *items):
    def constr(tag, state):
        return urwid.CheckBox(tag, state)
    d = CheckListDialogDisplay( text, height, width, constr, items, True)
    d.add_buttons([    ("OK", 0), ("Cancel", 1) ])
    return d

def do_inputbox(text, height, width):
    d = InputDialogDisplay( text, height, width )
    d.add_buttons([    ("Exit", 0) ])
    return d

def do_menu(text, height, width, menu_height, *items):
    def constr(tag, state ):
        return MenuItem(tag)
    d = ListDialogDisplay(text, height, width, constr, items, False)
    d.add_buttons([    ("OK", 0), ("Cancel", 1) ])
    return d

def do_msgbox(text, height, width):
    d = DialogDisplay( text, height, width )
    d.add_buttons([    ("OK", 0) ])
    return d

def do_radiolist(text, height, width, list_height, *items):
    radiolist = []
    def constr(tag, state, radiolist=radiolist):
        return urwid.RadioButton(radiolist, tag, state)
    d = ListDialogDisplay( text, height, width, constr, items, True )
    d.add_buttons([    ("OK", 0), ("Cancel", 1) ])
    return d

def do_textbox(file, height, width):
    d = TextDialogDisplay( file, height, width )
    d.add_buttons([    ("Exit", 0) ])
    return d

def do_yesno(text, height, width):
    d = DialogDisplay( text, height, width )
    d.add_buttons([    ("Yes", 0), ("No", 1) ])
    return d

MODES={    '--checklist':    (do_checklist,
        "text height width list-height [ tag item status ] ..."),
    '--inputbox':    (do_inputbox,
        "text height width"),
    '--menu':    (do_menu,
        "text height width menu-height [ tag item ] ..."),
    '--msgbox':    (do_msgbox,
        "text height width"),
    '--radiolist':    (do_radiolist,
        "text height width list-height [ tag item status ] ..."),
    '--textbox':    (do_textbox,
        "file height width"),
    '--yesno':    (do_yesno,
        "text height width"),
    }


def show_usage():
    """
    Display a helpful usage message.
    """
    modelist = [(mode, help) for (mode, (fn, help)) in MODES.items()]
    modelist.sort()
    sys.stdout.write(
        __doc__ +
        "\n".join(["%-15s %s"%(mode,help) for (mode,help) in modelist])
        + """

height and width may be set to 0 to auto-size.
list-height and menu-height are currently ignored.
status may be either on or off.
""" )


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        show_usage()
        return

    # Create a DialogDisplay instance
    fn, help = MODES[sys.argv[1]]
    d = fn( * sys.argv[2:] )

    # Run it
    exitcode, exitstring = d.main()

    # Exit
    if exitstring:
        sys.stderr.write(exitstring+"\n")

    sys.exit(exitcode)


if __name__=="__main__":
    main()
