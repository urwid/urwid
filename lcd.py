#!/usr/bin/python

"""
The crystalfontz 635 has these characters in ROM:

....X. ...... ......
...XX. .XXXXX ..XXX.
..XXX. .XXXXX .XXXXX
.XXXX. .XXXXX .XXXXX
..XXX. .XXXXX .XXXXX
...XX. .XXXXX ..XXX.
....X. ...... ......
...... ...... ......
  0x11   0xd0   0xbb

By adding the characters in CGRAM below we can use them as part of a 
horizontal slider control, selected check box and selected radio button
respectively.
"""

import urwid.lcd_display

CGRAM = """
...... ...... ...... ...... ..X... ...... ...... ...... 
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. .....X 
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X ....XX 
...... XX.... XXXX.. XXXXXX X.XXXX .X...X .X...X .X.XX. 
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X .XXX.. 
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. ..X... 
...... ...... ...... ...... ..X... ...... ...... ...... 
...... ...... ...... ...... ...... ...... ...... ...... 
"""

def program_cgram(screen):
    """
    Load the character data
    """
    # convert .'s and X's above into integer data
    cbuf = [list() for x in range(8)]
    for row in CGRAM.strip().split('\n'):
        rowsegments = row.strip().split()
        for num, r in enumerate(rowsegments):
            accum = 0
            for c in r:
                accum = (accum << 1) + (c == 'X')
            cbuf[num].append(accum)

    for num, cdata in enumerate(cbuf):
        screen.program_cgram(num, cdata)


class LCDCheckBox(urwid.CheckBox):
    """
    A check box+label that uses only one character for the check box
    """
    states = {
        True: urwid.SelectableIcon('\xd0', cursor_position=0),
        False: urwid.SelectableIcon('\x05', cursor_position=0),
    }
    reserve_columns = 1

class LCDRadioButton(urwid.RadioButton):
    """
    A radio button+label that uses only one character for the radio button
    """
    states = {
        True: urwid.SelectableIcon('\xbb', cursor_position=0),
        False: urwid.SelectableIcon('\x06', cursor_position=0),
    }
    reserve_columns = 1

class MenuOption(urwid.Button):
    """
    A menu option, indicated with a single arrow character
    """
    def __init__(self, label, submenu):
        self.__super.__init__("")
        # use a Text widget for label, we want the cursor
        # on the arrow not the label
        self._label = urwid.Text("")
        self.set_label(label)

        self._w = urwid.Columns([
            ('fixed', 1, urwid.SelectableIcon('\xdf', cursor_position=0)),
            self._label])

        urwid.connect_signal(self, 'click', 
            lambda option: show_menu(submenu))


class Menu(urwid.ListBox):
    def __init__(self, widgets):
        self.menu_parent = None
        self.__super.__init__(urwid.SimpleListWalker(widgets))

    def keypress(self, size, key):
        """
        Go back to the previous menu on cancel button (mapped to esc)
        """
        if urwid.command_map[key] == 'exit' and self.menu_parent:
            show_menu(self.menu_parent)
        else:
            return self.__super.keypress(size, key)

def build_menus():
    cursor_option_group = []
    def cursor_option(label, style):
        "a radio button that sets the cursor style"
        def on_change(b, state):
            if state: screen.set_cursor_style(style)
        b = LCDRadioButton(cursor_option_group, label,
            screen.cursor_style == style)
        urwid.connect_signal(b, 'change', on_change)
        return b

    menu_structure = [
        ('Display Settings', [
            LCDCheckBox('check'),
            LCDCheckBox('it out'),
            ]),
        ('Cursor Settings', [
            cursor_option('Block', screen.CURSOR_BLINKING_BLOCK),
            cursor_option('Underscore', screen.CURSOR_UNDERSCORE),
            cursor_option('Block + Underscore', 
                screen.CURSOR_BLINKING_BLOCK_UNDERSCORE),
            cursor_option('Inverting Block', 
                screen.CURSOR_INVERTING_BLINKING_BLOCK),
            ]),
        ('LEDs', [
            ]),
        ('About this Demo', [
            urwid.Text("This is a demo of Urwid's CF635Display "
                "module. If you need an interface for a limited "
                "character display device this should serve as a "
                "good example for implmenting your own display "
                "module and menu-driven application."),
            ])
        ]

    def build_submenu(ms):
        """
        Recursive menu building from structure above
        """
        options = []
        submenus = []
        for opt in ms:
            # shortform for MenuOptions
            if type(opt) == tuple:
                name, sub = opt
                submenu = build_submenu(sub)
                opt = MenuOption(name, submenu)
                submenus.append(submenu)
            options.append(opt)
        menu = Menu(options)
        for s in submenus:
            s.menu_parent = menu
        return menu
    return build_submenu(menu_structure)


screen = urwid.lcd_display.CF635Screen('/dev/ttyUSB0')
# set up our font
program_cgram(screen)
loop = urwid.MainLoop(build_menus(), screen=screen)
# FIXME: want screen to know it is in narrow mode, or better yet, 
# do the unicode conversion for us
urwid.set_encoding('narrow')
# customize command keys
urwid.command_map['enter'] = 'activate' # this is a default
urwid.command_map['right'] = 'activate'
urwid.command_map['esc'] = 'exit'
urwid.command_map['left'] = 'exit'


def show_menu(menu):
    loop.widget = menu

loop.run()

