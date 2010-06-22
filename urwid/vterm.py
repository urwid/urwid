#!/usr/bin/python
#
# Urwid terminal emulation widget
#    Copyright (C) 2010  aszlig
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

import os
import pty
import time
import fcntl
import struct
import signal
import atexit
import termios

import urwid

ESC = chr(27)

KEY_TRANSLATIONS = {
    'enter':     chr(13),
    'backspace': chr(127),
    'tab':       chr(9),
    'esc':       ESC,
    'up':        ESC + '[A',
    'down':      ESC + '[B',
    'right':     ESC + '[C',
    'left':      ESC + '[D',
    'home':      ESC + '[1~',
    'end':       ESC + '[4~',
    'page up':   ESC + '[5~',
    'page down': ESC + '[6~',

    'f1':        ESC + '[[A',
    'f2':        ESC + '[[B',
    'f3':        ESC + '[[C',
    'f4':        ESC + '[[D',
    'f5':        ESC + '[[E',
    'f6':        ESC + '[17~',
    'f7':        ESC + '[18~',
    'f8':        ESC + '[19~',
    'f9':        ESC + '[20~',
    'f10':       ESC + '[21~',
    'f11':       ESC + '[23~',
    'f12':       ESC + '[24~',
}

CSI_COMMANDS = {
    # possible values:
    #     None -> ignore sequence
    #     (<minimum number of args>, callback)
    #     ('alias', <symbol>)
    #
    # while callback is executed as:
    #     callback(<instance of TermCanvas>, arguments, has_question_mark)

    '@': (1, lambda s, (number,), q: s.insert_chars(chars=number)),
    'A': (1, lambda s, (rows,), q: s.move_cursor(0, -rows, relative=True)),
    'B': (1, lambda s, (rows,), q: s.move_cursor(0, rows, relative=True)),
    'C': (1, lambda s, (cols,), q: s.move_cursor(cols, 0, relative=True)),
    'D': (1, lambda s, (cols,), q: s.move_cursor(-cols, 0, relative=True)),
    'E': (1, lambda s, (rows,), q: s.move_cursor(0, rows, relative_y=True)),
    'F': (1, lambda s, (rows,), q: s.move_cursor(0, -rows, relative_y=True)),
    'G': (1, lambda s, (col,), q: s.move_cursor(col - 1, 0, relative_y=True)),
    'H': (2, lambda s, (x, y), q: s.move_cursor(y - 1, x - 1)),
    'J': (1, lambda s, (mode,), q: s.csi_erase_display(mode)),
    'K': (1, lambda s, (mode,), q: s.csi_erase_line(mode)),
    'L': (1, lambda s, (number,), q: s.insert_lines(lines=number)),
    'M': (1, lambda s, (number,), q: s.remove_lines(lines=number)),
    'P': (1, lambda s, (number,), q: s.remove_chars(chars=number)),
    'X': (1, lambda s, (number,), q: s.erase(s.cursor, (s.cursor[0]+number-1,
                                                        s.cursor[1]))),
    'a': ('alias', 'C'),
    'c': (0, lambda s, (t,), q: None if q else s.widget.respond(ESC + '[?6c')),
    'd': (1, lambda s, (row,), q: s.move_cursor(0, row - 1, relative_x=True)),
    'e': ('alias', 'B'),
    'f': ('alias', 'H'),
    'g': None,
    'h': None,
    'l': None,
    'm': (1, lambda s, attrs, q: s.csi_set_attr(attrs)),
    'n': (1, lambda s, (mode,), q: s.csi_status_report(mode)),
    'q': None,
    'r': None,
    's': None,
    'u': None,
    '`': ('alias', 'G'),
}

class TermCanvas(urwid.Canvas):
    cacheable = False

    def __init__(self, width, height, widget):
        urwid.Canvas.__init__(self)

        self.width, self.height = width, height
        self.widget = widget

        self.scrollback_buffer = []

        self.escbuf = ''
        self.within_escape = False
        self.parsestate = 0
        self.attrspec = None

        # initialize self.term
        self.clear()

    def empty_line(self, char=' '):
        return [self.empty_char(char)] * self.width

    def empty_char(self, char=' '):
        return (self.attrspec, None, char)

    def addstr(self, data):
        x, y = self.cursor
        for char in data:
            self.addch(char)

    def resize(self, width, height):
        if width > self.width:
            for y in xrange(self.height):
                self.term[y] += [self.empty_char()] * (width - self.width)
        elif width < self.width:
            for y in xrange(self.height):
                self.term[y] = self.term[y][:width]

        self.width = width

        if height > self.height:
            for y in xrange(height - self.height):
                self.term.append(self.empty_line())
        elif height < self.height:
            for y in xrange(self.height - height):
                self.term.pop(0)

        self.height = height

        x, y = self.constrain_coords(*self.cursor)
        self.cursor = (x, y)

    def parse_csi(self, char):
        qmark = self.escbuf.startswith('?')

        escbuf = []
        for arg in self.escbuf[qmark and 1 or 0:].split(';'):
            try:
                num = int(arg)
            except ValueError:
                num = 0

            escbuf.append(num)

        if CSI_COMMANDS[char] is not None:
            if CSI_COMMANDS[char][0] == 'alias':
                csi_cmd = CSI_COMMANDS[(CSI_COMMANDS[char][1])]
            else:
                csi_cmd = CSI_COMMANDS[char]

            number_of_args, cmd = csi_cmd
            while len(escbuf) < number_of_args:
                escbuf.append(0)
            cmd(self, escbuf, qmark)

    def parse_noncsi(self, char, mod=None):
        if mod == '#' and char == '8':
            self.decaln()

    def parse_escape(self, char):
        if self.parsestate == 1:
            # within CSI
            if char in CSI_COMMANDS.keys():
                self.parse_csi(char)
                self.parsestate = 0
            elif char in '0123456789;' or (self.escbuf == '' and char == '?'):
                self.escbuf += char
                return
        elif self.parsestate == 0 and char == '[':
            # start of CSI
            self.escbuf = ''
            self.parsestate = 1
            return
        elif self.parsestate == 0 and char in ('%', '#', '(', ')'):
            # non-CSI sequence
            self.escbuf = char
            self.parsestate = 3
            return
        elif self.parsestate == 3:
            self.parse_noncsi(char, self.escbuf)
        elif char in ('c', 'D', 'E', 'H', 'M', 'Z', '7', '8', '>', '='):
            self.parse_noncsi(char)

        self.within_escape = False
        self.parsestate = 0
        self.escbuf = ''

    def addch(self, char):
        """
        Add a single character to the terminal state machine.
        """
        x, y = self.cursor

        if char == chr(27): # escape
            self.within_escape = True
        elif char == chr(13): # carriage return
            self.cursor = (0, y)
        elif char in (chr(10), chr(11), chr(12)): # line feed
            self.newline()
        elif char == chr(12): # form feed
            self.clear()
        elif char == chr(9): # char tab
            self.tab()
        elif char == chr(8): # backspace
            if x > 0:
                self.cursor = (x - 1, y)
        elif char == chr(11): # line tab
            if y > 0:
                self.cursor = (x, y - 1)
        elif char == chr(7): # beep
            self.widget.beep()
        elif self.within_escape:
            self.parse_escape(char)
        else:
            self.push_cursor(char)

    def set_char(self, char, x=None, y=None):
        """
        Set character of either the current cursor position
        or a position given by 'x' and/or 'y' to 'char'.
        """
        if x is None:
            x = self.cursor[0]
        if y is None:
            y = self.cursor[1]

        x, y = self.constrain_coords(x, y)
        self.term[y][x] = (self.attrspec, None, char)

    def constrain_coords(self, x, y):
        """
        Checks if x/y are within the terminal and returns the corrected version.
        """
        if x >= self.width:
            x = self.width - 1
        elif x < 0:
            x = 0

        if y >= self.height:
            y = self.height - 1
        elif y < 0:
            y = 0

        return x, y

    def newline(self):
        """
        Move the cursor down one line but don't reset horizontal
        position.
        """
        x, y = self.cursor

        if y >= self.height - 1:
            self.scroll()
        else:
            y += 1

        self.cursor = (x, y)

    def move_cursor(self, x, y, relative_x=False, relative_y=False,
                    relative=False):
        """
        Move cursor to position x/y while constraining terminal sizes.
        If 'relative' is True, x/y is relative to the current cursor
        position. 'relative_x' and 'relative_y' is the same but just with
        the corresponding axis.
        """
        if relative:
            relative_y = relative_x = True

        if relative_x:
            x = self.cursor[0] + x
        if relative_y:
            y = self.cursor[1] + y

        x, y = self.constrain_coords(x, y)

        self.cursor = (x, y)

    def push_cursor(self, char=None):
        """
        Move cursor one character forward wrapping lines as needed.
        If 'char' is given, put the character into the former position.
        """
        x, y = self.cursor

        if char is not None:
            self.set_char(char)

        x += 1

        if x >= self.width:
            if y >= self.height - 1:
                self.scroll()
            else:
                y += 1

            x = 0

        self.cursor = (x, y)

    def tab(self, tabstop=8):
        """
        Moves cursor to the next 'tabstop' filling everything in between
        with spaces.
        """
        x, y = self.cursor

        while x < self.width:
            self.set_char(" ")
            x += 1

            if x % tabstop == 0:
                break

        self.cursor = x, y

    def scroll(self):
        """
        Append a new line at the bottom and put the topmost line into the
        scrollback buffer.
        """
        killed = self.term.pop(0)
        self.scrollback_buffer.append(killed)
        self.term.append(self.empty_line())

    def decaln(self):
        """
        DEC screen alignment test.
        Fill screen with E's form top to current line.
        """
        for row in xrange(self.cursor[1] + 1):
            self.term[row] = self.empty_line('E')

    def blank_line(self, row):
        """
        Blank a single line at the specified row, without modifying other lines.
        """
        self.term[row] = self.empty_line()

    def insert_chars(self, position=None, chars=1):
        """
        Insert 'chars' number of empty characters before 'position' (or the
        current position if not specified) pushing subsequent characters of the
        line to the right without wrapping.
        """
        if position is None:
            position = self.cursor

        if chars == 0:
            chars = 1

        x, y = position

        while chars > 0:
            self.term[y].insert(x, self.empty_char())
            self.term[y].pop()
            chars -= 1

    def remove_chars(self, position=None, chars=1):
        """
        Remove 'chars' number of empty characters from 'position' (or the current
        position if not specified) pulling subsequent characters of the line to
        the left without joining any subsequent lines.
        """
        if position is None:
            position = self.cursor

        if chars == 0:
            chars = 1

        x, y = position

        while chars > 0:
            self.term[y].pop(x)
            self.term[y].append(self.empty_char())
            chars -= 1

    def insert_lines(self, row=None, lines=1):
        """
        Insert 'lines' of empty lines after the specified row, pushing all
        subsequent lines to the bottom. If no 'row' is specified, the current
        row is used.
        """
        if row is None:
            row = self.cursor[1]

        if lines == 0:
            lines = 1

        while lines > 0:
            self.term.insert(row, self.empty_line())
            self.term.pop()
            lines -= 1

    def remove_lines(self, row=None, lines=1):
        """
        Remove 'lines' number of lines at the specified row, pulling all
        subsequent lines to the top. If no 'row' is specified, the current row
        is used.
        """
        if row is None:
            row = self.cursor[1]

        if lines == 0:
            lines = 1

        while lines > 0:
            self.term.pop(row)
            self.term.append(self.empty_line())
            lines -= 1

    def erase(self, start, end):
        """
        Erase a region of the terminal. The 'start' tuple (x, y) defines the
        starting position of the erase, while end (x, y) the last position.

        For example if the terminal size is 4x3, start=(1, 1) and end=(1, 2)
        would erase the following region:

        ....
        .XXX
        XX..
        """
        sx, sy = self.constrain_coords(*start)
        ex, ey = self.constrain_coords(*end)

        # within a single row
        if sy == ey:
            for x in xrange(sx, ex + 1):
                self.term[sy][x] = self.empty_char()
            return

        # spans multiple rows
        y = sy
        while y <= ey:
            if y == sy:
                for x in xrange(sx, self.width):
                    self.term[y][x] = self.empty_char()
            elif y == ey:
                for x in xrange(ex + 1):
                    self.term[y][x] = self.empty_char()
            else:
                self.blank_line(y)

            y += 1

    def sgi_to_attrspec(self, attrs, fg, bg, attributes):
        for attr in attrs:
            if 30 <= attr <= 37:
                fg = attr - 30
            elif 40 <= attr <= 47:
                bg = attr - 40
            elif attr == 38:
                # set default foreground color, set underline
                attributes.add('underline')
                fg = None
            elif attr == 39:
                # set default foreground color, remove underline
                attributes.discard('underline')
                fg = None
            elif attr == 49:
                # set default background color
                bg = None

            # set attributes
            elif attr == 1:
                attributes.add('bold')
            elif attr == 4:
                attributes.add('underline')
            elif attr == 7:
                attributes.add('standout')

            # unset attributes
            elif attr == 24:
                attributes.discard('underline')
            elif attr == 27:
                attributes.discard('standout')
            elif attr == 0:
                # clear all attributes
                fg = bg = None
                attributes.clear()

        if 'bold' in attributes and fg is not None:
            fg += 8

        defaulter = lambda a: 'default' if a is None else \
                              urwid.display_common._BASIC_COLORS[a]

        fg = defaulter(fg)
        bg = defaulter(bg)

        if len(attributes) > 0:
            fg = ','.join([fg] + list(attributes))

        if fg == 'default' and bg == 'default':
            return None
        else:
            return urwid.AttrSpec(fg, bg)

    def csi_set_attr(self, attrs):
        """
        Set graphics rendition.
        """
        if attrs[-1] == 0:
            self.attrspec = None

        attributes = set()
        if self.attrspec is None:
            fg = bg = None
        else:
            # set default values from previous attrspec
            fg = self.attrspec.foreground_number
            bg = self.attrspec.background_number
            if fg >= 8: fg -= 8
            if bg >= 8: bg -= 8
            for attr in ('bold', 'underline', 'standout'):
                if not getattr(self.attrspec, attr):
                    continue

                attributes.add(attr)

        self.attrspec = self.sgi_to_attrspec(attrs, fg, bg, attributes)

    def csi_status_report(self, mode):
        """
        Report various information about the terminal status.
        Information is queried by 'mode', where possible values are:
            5 -> device status report
            6 -> cursor position report
        """
        if mode == 5:
            # terminal OK
            self.widget.respond(ESC + '[0n')
        elif mode == 6:
            x, y = self.cursor
            self.widget.respond(ESC + '[%d;%dR' % (y + 1, x + 1))

    def csi_erase_line(self, mode):
        """
        Erase current line, modes are:
            0 -> erase from cursor to end of line.
            1 -> erase from start of line to cursor.
            2 -> erase whole line.
        """
        x, y = self.cursor

        if mode == 0:
            self.erase(self.cursor, (self.width - 1, y))
        elif mode == 1:
            self.erase((0, y), (x - 1, y))
        elif mode == 2:
            self.blank_line(y)

    def csi_erase_display(self, mode):
        """
        Erase display, modes are:
            0 -> erase from cursor to end of display.
            1 -> erase from start to cursor.
            2 -> erase the whole display.
        """
        if mode == 0:
            self.erase(self.cursor, (self.width - 1, self.height - 1))
        if mode == 1:
            self.erase((0, 0), (self.cursor[0] - 1, self.cursor[1]))
        elif mode == 2:
            self.clear(cursor=self.cursor)

    def clear(self, cursor=None):
        """
        Clears the whole terminal screen and resets the cursor position
        to (0, 0) or to the coordinates given by 'cursor'.
        """
        self.term = [self.empty_line() for x in xrange(self.height)]

        if cursor is None:
            self.cursor = (0, 0)
        else:
            self.cursor = cursor

    def cols(self):
        return self.width

    def rows(self):
        return self.height

    def content(self, trim_left=0, trim_right=0, cols=None, rows=None,
                attr_map=None):
        for line in self.term:
            yield line

    def content_delta(self, other):
        if other is self:
            return [self.cols()]*self.rows()
        return self.content()

class TerminalWidget(urwid.BoxWidget):
    signals = ['closed', 'beep']

    def __init__(self, command, event_loop, escape_sequence=None):
        self.__super.__init__()

        if escape_sequence is None:
            self.escape_sequence = "ctrl a"
        else:
            self.escape_sequence = escape_sequence

        if command is None:
            self.command = [os.getenv('SHELL')]
        else:
            self.command = command

        self._default_handler = signal.getsignal(signal.SIGINT)

        self.escape_mode = False
        self.response_buffer = []

        self.event_loop = event_loop

        self.master = None
        self.pid = None

        self.width = None
        self.height = None
        self.term = None
        self.has_focus = False
        self.terminated = False

    def spawn(self):
        env = dict(os.environ)
        env['TERM'] = 'linux'

        self.pid, self.master = pty.fork()

        if self.pid == 0:
            os.execvpe(self.command[0], self.command, env)
            # this should never be reached!
            os._exit(0)

        atexit.register(self.terminate)

    def terminate(self):
        if self.terminated:
            return

        self.terminated = True
        self.remove_watch()
        self.change_focus(False)

        if self.pid > 0:
            self.set_termsize(0, 0)
            for sig in (signal.SIGHUP, signal.SIGCONT, signal.SIGINT,
                        signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(self.pid, sig)
                    pid, status = os.waitpid(self.pid, os.WNOHANG)
                except OSError:
                    break

                if pid == 0:
                    break
                time.sleep(0.1)
            try:
                os.waitpid(self.pid, 0)
            except OSError:
                pass

            os.close(self.master)

    def beep(self):
        self._emit('beep')

    def respond(self, string):
        """
        Respond to the underlying application with 'string'.
        """
        self.response_buffer.append(string)

    def flush_responses(self):
        for string in self.response_buffer:
            os.write(self.master, string)
        self.response_buffer = []

    def set_termsize(self, width, height):
        winsize = struct.pack("HHHH", height, width, 0, 0)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, winsize)

    def touch_term(self, width, height):
        process_opened = False

        if self.pid is None:
            self.spawn()
            process_opened = True

        if self.width == width and self.height == height:
            return

        self.set_termsize(width, height)

        if not self.term:
            self.term = TermCanvas(width, height, self)
        else:
            self.term.resize(width, height)

        self.width = width
        self.height = height

        if process_opened:
            self.add_watch()

    def propagate_sigint(self, sig, stack):
        if sig == signal.SIGINT:
            self.escape_mode = False
            os.write(self.master, chr(3))

    def change_focus(self, has_focus):
        """
        Ignore SIGINT if this widget has focus.
        """
        if self.has_focus == has_focus:
            return

        self.has_focus = has_focus

        if has_focus:
            signal.signal(signal.SIGINT, self.propagate_sigint)
        else:
            signal.signal(signal.SIGINT, self._default_handler)

    def render(self, size, focus=False):
        if not self.terminated:
            self.change_focus(focus)

            width, height = size
            self.touch_term(width, height)

        return self.term

    def add_watch(self):
        self.event_loop.watch_file(self.master, self.feed)

    def remove_watch(self):
        self.event_loop.remove_watch_file(self.master)

    def selectable(self):
        return True

    def feed(self):
        try:
            data = os.read(self.master, 4096)
        except OSError: # End Of File
            self.terminate()
            self._emit('closed')
            return
        self.term.addstr(data)

        self.flush_responses()

        # XXX: any "nicer" way of doing this?
        for update_method in self.event_loop._watch_files.values():
            if update_method.im_class.__name__ != 'MainLoop':
                continue

            update_method.im_self.draw_screen()
            break

    def keypress(self, size, key):
        if self.terminated:
            return key

        if key == "window resize":
            width, height = size
            self.touch_term(width, height)
            return

        if self.escape_mode and self.escape_sequence == key:
            # twice the escape key will pass
            # it once to the terminal
            self.escape_mode = False
        elif self.escape_mode:
            # pass through the keypress
            self.escape_mode = False
            return key
        elif self.escape_sequence == key:
            # don't handle next keypress
            self.change_focus(False)
            self.escape_mode = True
            return

        if key.startswith("ctrl "):
            if key == 'c':
                # C-c is handled by propagate_sigint()
                return

            if key[-1].islower():
                key = chr(ord(key[-1]) - ord('a') + 1)
            else:
                key = chr(ord(key[-1]) - ord('A') + 1)
        else:
            key = KEY_TRANSLATIONS.get(key, key)

        os.write(self.master, key)

if __name__ == '__main__':
    event_loop = urwid.SelectEventLoop()

    mainframe = urwid.Frame(
        urwid.Pile([
            urwid.Columns([
                urwid.SolidFill('['),
                ('weight', 70, TerminalWidget(None, event_loop)),
                urwid.SolidFill(']'),
            ], box_columns=[1]),
            ('fixed', 1, urwid.Filler(urwid.Edit('focus test edit: '))),
        ]),
        header=urwid.Text('some header'),
        footer=urwid.Text('some footer')
    )

    def quit(key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    loop = urwid.MainLoop(
        mainframe,
        unhandled_input=quit,
        event_loop=event_loop
    ).run()
