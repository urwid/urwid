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
        if key == 'esc' and self.menu_parent:
            show_menu(self.menu_parent)
        else:
            return self.__super.keypress(size, key)

def build_menus():
    cursor_option_group = []

    m_display = Menu([
        LCDCheckBox('check'),
        LCDCheckBox('it out'),
        ])
    m_cursor = Menu([
        LCDRadioButton(cursor_option_group, "one"),
        LCDRadioButton(cursor_option_group, "two"),
        LCDRadioButton(cursor_option_group, "three"),
        ])
    m_leds = Menu([])
    m_about = Menu([urwid.Text("some about text")])

    o_display = MenuOption('Display Settings', m_display)
    o_cursor = MenuOption('Cursor Settings', m_cursor)
    o_leds = MenuOption('LEDs', m_leds)
    o_about = MenuOption('About this Demo', m_about)

    m_root = Menu([o_display, o_cursor, o_leds, o_about])
    m_display.menu_parent = m_cursor.menu_parent = m_root
    m_leds.menu_parent = m_about.menu_parent = m_root

    return m_root

screen = urwid.lcd_display.CF635Screen('/dev/ttyUSB0')
# set up our font
program_cgram(screen)
loop = urwid.MainLoop(build_menus(), screen=screen)
# FIXME: want screen to know it is in narrow mode, or better yet, 
# do the unicode conversion for us
urwid.set_encoding('narrow')

def show_menu(menu):
    loop.widget = menu

loop.run()

