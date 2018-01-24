#!/usr/bin/env python

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

import sys
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
    A check box+label that uses only one character for the check box,
    including custom CGRAM character
    """
    states = {
        True: urwid.SelectableIcon('\xd0'),
        False: urwid.SelectableIcon('\x05'),
    }
    reserve_columns = 1

class LCDRadioButton(urwid.RadioButton):
    """
    A radio button+label that uses only one character for the radio button,
    including custom CGRAM character
    """
    states = {
        True: urwid.SelectableIcon('\xbb'),
        False: urwid.SelectableIcon('\x06'),
    }
    reserve_columns = 1

class LCDProgressBar(urwid.FlowWidget):
    """
    The "progress bar" used by the horizontal slider for this device,
    using custom CGRAM characters
    """
    segments = '\x00\x01\x02\x03'
    def __init__(self, range, value):
        self.range = range
        self.value = value

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        """
        Draw the bar with self.segments where [0] is empty and [-1]
        is completely full
        """
        (maxcol,) = size
        steps = self.get_steps(size)
        filled = urwid.int_scale(self.value, self.range, steps)
        full_segments = int(filled / (len(self.segments) - 1))
        last_char = filled % (len(self.segments) - 1) + 1
        s = (self.segments[-1] * full_segments +
            self.segments[last_char] +
            self.segments[0] * (maxcol -full_segments - 1))
        return urwid.Text(s).render(size)

    def move_position(self, size, direction):
        """
        Update and return the value one step +ve or -ve, based on
        the size of the displayed bar.

        direction -- 1 for +ve, 0 for -ve
        """
        steps = self.get_steps(size)
        filled = urwid.int_scale(self.value, self.range, steps)
        filled += 2 * direction - 1
        value = urwid.int_scale(filled, steps, self.range)
        value = max(0, min(self.range - 1, value))
        if value != self.value:
            self.value = value
            self._invalidate()
        return value

    def get_steps(self, size):
        """
        Return the number of steps available given size for rendering
        the bar and number of segments we can draw.
        """
        (maxcol,) = size
        return maxcol * (len(self.segments) - 1)


class LCDHorizontalSlider(urwid.WidgetWrap):
    """
    A slider control using custom CGRAM characters
    """
    def __init__(self, range, value, callback):
        self.bar = LCDProgressBar(range, value)
        cols = urwid.Columns([
            ('fixed', 1, urwid.SelectableIcon('\x11')),
            self.bar,
            ('fixed', 1, urwid.SelectableIcon('\x04')),
            ])
        self.__super.__init__(cols)
        self.callback = callback

    def keypress(self, size, key):
        # move the slider based on which arrow is focused
        if key == 'enter':
            # use the correct size for adjusting the bar
            self.bar.move_position((self._w.column_widths(size)[1],),
                self._w.get_focus_column() != 0)
            self.callback(self.bar.value)
        else:
            return self.__super.keypress(size, key)



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
            ('fixed', 1, urwid.SelectableIcon('\xdf')),
            self._label])

        urwid.connect_signal(self, 'click',
            lambda option: show_menu(submenu))

    def keypress(self, size, key):
        if key == 'right':
            key = 'enter'
        return self.__super.keypress(size, key)


class Menu(urwid.ListBox):
    def __init__(self, widgets):
        self.menu_parent = None
        self.__super.__init__(urwid.SimpleListWalker(widgets))

    def keypress(self, size, key):
        """
        Go back to the previous menu on cancel button (mapped to esc)
        """
        key = self.__super.keypress(size, key)
        if key in ('left', 'esc') and self.menu_parent:
            show_menu(self.menu_parent)
        else:
            return key

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

    def display_setting(label, range, fn):
        slider = LCDHorizontalSlider(range, range/2, fn)
        return urwid.Columns([
            urwid.Text(label),
            ('fixed', 10, slider),
            ])

    def led_custom(index):
        def exp_scale_led(rg):
            """
            apply an exponential transformation to values sent so
            that apparent brightness increases in a natural way.
            """
            return lambda value: screen.set_led_pin(index, rg,
                [0, 1, 2, 3, 4, 5, 6, 8, 11, 14, 18,
                23, 29, 38, 48, 61, 79, 100][value])

        return urwid.Columns([
            ('fixed', 2, urwid.Text('%dR' % index)),
            LCDHorizontalSlider(18, 0, exp_scale_led(0)),
            ('fixed', 2, urwid.Text(' G')),
            LCDHorizontalSlider(18, 0, exp_scale_led(1)),
            ])

    menu_structure = [
        ('Display Settings', [
            display_setting('Brightness', 101, screen.set_backlight),
            display_setting('Contrast', 76,
                lambda x: screen.set_lcd_contrast(x + 75)),
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
            led_custom(0),
            led_custom(1),
            led_custom(2),
            led_custom(3),
            ]),
        ('About this Demo', [
            urwid.Text("This is a demo of Urwid's CF635Display "
                "module. If you need an interface for a limited "
                "character display device this should serve as a "
                "good example for implementing your own display "
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


screen = urwid.lcd_display.CF635Screen(sys.argv[1])
# set up our font
program_cgram(screen)
loop = urwid.MainLoop(build_menus(), screen=screen)
# FIXME: want screen to know it is in narrow mode, or better yet,
# do the unicode conversion for us
urwid.set_encoding('narrow')


def show_menu(menu):
    loop.widget = menu

loop.run()

