#!/usr/bin/python
#
# Urwid raw display module
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
Direct terminal UI implementation
"""

import fcntl
import termios
import os
import select
import struct
import sys
import tty
import signal

from urwid import util
from urwid import escape
from urwid.display_common import BaseScreen, RealTerminal, \
    UPDATE_PALETTE_ENTRY, AttrSpec, UNPRINTABLE_TRANS_TABLE, \
    INPUT_DESCRIPTORS_CHANGED
from urwid import signals
from urwid.compat import PYTHON3, bytes, B

from subprocess import Popen, PIPE


class Screen(BaseScreen, RealTerminal):
    def __init__(self):
        """Initialize a screen that directly prints escape codes to an output
        terminal.
        """
        super(Screen, self).__init__()
        self._pal_escape = {}
        signals.connect_signal(self, UPDATE_PALETTE_ENTRY, 
            self._on_update_palette_entry)
        self.colors = 16 # FIXME: detect this
        self.has_underline = True # FIXME: detect this
        self.register_palette_entry( None, 'default','default')
        self._keyqueue = []
        self.prev_input_resize = 0
        self.set_input_timeouts()
        self.screen_buf = None
        self._screen_buf_canvas = None
        self._resized = False
        self.maxrow = None
        self.gpm_mev = None
        self.gpm_event_pending = False
        self.last_bstate = 0
        self._setup_G1_done = False
        self._rows_used = None
        self._cy = 0
        self.bright_is_bold = os.environ.get('TERM',None) != "xterm"
        self._next_timeout = None
        self._term_output_file = sys.stdout
        self._term_input_file = sys.stdin
        # pipe for signalling external event loops about resize events
        self._resize_pipe_rd, self._resize_pipe_wr = os.pipe()
        fcntl.fcntl(self._resize_pipe_rd, fcntl.F_SETFL, os.O_NONBLOCK)

    def _on_update_palette_entry(self, name, *attrspecs):
        # copy the attribute to a dictionary containing the escape seqences
        self._pal_escape[name] = self._attrspec_to_escape(
            attrspecs[{16:0,1:1,88:2,256:3}[self.colors]])

    def set_input_timeouts(self, max_wait=None, complete_wait=0.125, 
        resize_wait=0.125):
        """
        Set the get_input timeout values.  All values are in floating
        point numbers of seconds.
        
        max_wait -- amount of time in seconds to wait for input when
            there is no input pending, wait forever if None
        complete_wait -- amount of time in seconds to wait when
            get_input detects an incomplete escape sequence at the
            end of the available input
        resize_wait -- amount of time in seconds to wait for more input
            after receiving two screen resize requests in a row to
            stop Urwid from consuming 100% cpu during a gradual
            window resize operation
        """
        self.max_wait = max_wait
        if max_wait is not None:
            if self._next_timeout is None:
                self._next_timeout = max_wait
            else:
                self._next_timeout = min(self._next_timeout, self.max_wait)
        self.complete_wait = complete_wait
        self.resize_wait = resize_wait

    def _sigwinch_handler(self, signum, frame):
        if not self._resized:
            os.write(self._resize_pipe_wr, B('R'))
        self._resized = True
        self.screen_buf = None
      
    def signal_init(self):
        """
        Called in the startup of run wrapper to set the SIGWINCH 
        signal handler to self._sigwinch_handler.

        Override this function to call from main thread in threaded
        applications.
        """
        signal.signal(signal.SIGWINCH, self._sigwinch_handler)
    
    def signal_restore(self):
        """
        Called in the finally block of run wrapper to restore the
        SIGWINCH handler to the default handler.

        Override this function to call from main thread in threaded
        applications.
        """
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)
      
    def set_mouse_tracking(self):
        """
        Enable mouse tracking.  
        
        After calling this function get_input will include mouse
        click events along with keystrokes.
        """
        self._term_output_file.write(escape.MOUSE_TRACKING_ON)

        self._start_gpm_tracking()
    
    def _start_gpm_tracking(self):
        if not os.path.isfile("/usr/bin/mev"):
            return
        if not os.environ.get('TERM',"").lower().startswith("linux"):
            return
        if not Popen:
            return
        m = Popen(["/usr/bin/mev","-e","158"], stdin=PIPE, stdout=PIPE,
            close_fds=True)
        fcntl.fcntl(m.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
        self.gpm_mev = m
    
    def _stop_gpm_tracking(self):
        os.kill(self.gpm_mev.pid, signal.SIGINT)
        os.waitpid(self.gpm_mev.pid, 0)
        self.gpm_mev = None
    
    def start(self, alternate_buffer=True):
        """
        Initialize the screen and input mode.

        alternate_buffer -- use alternate screen buffer
        """
        assert not self._started
        if alternate_buffer:
            self._term_output_file.write(escape.SWITCH_TO_ALTERNATE_BUFFER)
            self._rows_used = None
        else:
            self._rows_used = 0

        fd = self._term_input_file.fileno()
        if os.isatty(fd):
            self._old_termios_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)

        self.signal_init()
        self._alternate_buffer = alternate_buffer
        self._input_iter = self._run_input_iter()
        self._next_timeout = self.max_wait

        if not self._signal_keys_set:
            self._old_signal_keys = self.tty_signal_keys(fileno=fd)

        super(Screen, self).start()

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)


    def stop(self):
        """
        Restore the screen.
        """
        self.clear()
        if not self._started:
            return

        signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)

        self.signal_restore()

        fd = self._term_input_file.fileno()
        if os.isatty(fd):
            termios.tcsetattr(fd, termios.TCSADRAIN,
        self._old_termios_settings)

        move_cursor = ""
        if self.gpm_mev:
            self._stop_gpm_tracking()
        if self._alternate_buffer:
            move_cursor = escape.RESTORE_NORMAL_BUFFER
        elif self.maxrow is not None:
            move_cursor = escape.set_cursor_position( 
                0, self.maxrow)
        self._term_output_file.write(self._attrspec_to_escape(AttrSpec('','')) 
            + escape.SI
            + escape.MOUSE_TRACKING_OFF
            + escape.SHOW_CURSOR
            + move_cursor + "\n" + escape.SHOW_CURSOR )
        self._input_iter = self._fake_input_iter()

        if self._old_signal_keys:
            self.tty_signal_keys(*(self._old_signal_keys + (fd,)))

        super(Screen, self).stop()


    def run_wrapper(self, fn, alternate_buffer=True):
        """
        Call start to initialize screen, then call fn.  
        When fn exits call stop to restore the screen to normal.

        alternate_buffer -- use alternate screen buffer and restore
            normal screen buffer on exit
        """
        try:
            self.start(alternate_buffer)
            return fn()
        finally:
            self.stop()

    def get_input(self, raw_keys=False):
        """Return pending input as a list.

        raw_keys -- return raw keycodes as well as translated versions

        This function will immediately return all the input since the
        last time it was called.  If there is no input pending it will
        wait before returning an empty list.  The wait time may be
        configured with the set_input_timeouts function.

        If raw_keys is False (default) this function will return a list
        of keys pressed.  If raw_keys is True this function will return
        a ( keys pressed, raw keycodes ) tuple instead.

        Examples of keys returned:

        * ASCII printable characters:  " ", "a", "0", "A", "-", "/" 
        * ASCII control characters:  "tab", "enter"
        * Escape sequences:  "up", "page up", "home", "insert", "f1"
        * Key combinations:  "shift f1", "meta a", "ctrl b"
        * Window events:  "window resize"

        When a narrow encoding is not enabled:

        * "Extended ASCII" characters:  "\\xa1", "\\xb2", "\\xfe"

        When a wide encoding is enabled:

        * Double-byte characters:  "\\xa1\\xea", "\\xb2\\xd4"

        When utf8 encoding is enabled:

        * Unicode characters: u"\\u00a5", u'\\u253c"

        Examples of mouse events returned:

        * Mouse button press: ('mouse press', 1, 15, 13), 
                              ('meta mouse press', 2, 17, 23)
        * Mouse drag: ('mouse drag', 1, 16, 13),
                      ('mouse drag', 1, 17, 13),
                      ('ctrl mouse drag', 1, 18, 13)
        * Mouse button release: ('mouse release', 0, 18, 13),
                                ('ctrl mouse release', 0, 17, 23)
        """
        assert self._started

        self._wait_for_input_ready(self._next_timeout)
        self._next_timeout, keys, raw = self._input_iter.next()

        # Avoid pegging CPU at 100% when slowly resizing
        if keys==['window resize'] and self.prev_input_resize:
            while True:
                self._wait_for_input_ready(self.resize_wait)
                self._next_timeout, keys, raw2 = \
                    self._input_iter.next()
                raw += raw2
                #if not keys:
                #    keys, raw2 = self._get_input( 
                #        self.resize_wait)
                #    raw += raw2
                if keys!=['window resize']:
                    break
            if keys[-1:]!=['window resize']:
                keys.append('window resize')

        if keys==['window resize']:
            self.prev_input_resize = 2
        elif self.prev_input_resize == 2 and not keys:
            self.prev_input_resize = 1
        else:
            self.prev_input_resize = 0

        if raw_keys:
            return keys, raw
        return keys

    def get_input_descriptors(self):
        """
        Return a list of integer file descriptors that should be
        polled in external event loops to check for user input.

        Use this method if you are implementing yout own event loop.
        """
        if not self._started:
            return []

        fd_list = [self._term_input_file.fileno(), self._resize_pipe_rd]
        if self.gpm_mev is not None:
            fd_list.append(self.gpm_mev.stdout.fileno())
        return fd_list

    def get_input_nonblocking(self):
        """
        Return a (next_input_timeout, keys_pressed, raw_keycodes)
        tuple.

        Use this method if you are implementing your own event loop.

        When there is input waiting on one of the descriptors returned
        by get_input_descriptors() this method should be called to
        read and process the input.

        This method expects to be called in next_input_timeout seconds
        (a floating point number) if there is no input waiting.
        """
        return self._input_iter.next()

    def _run_input_iter(self):
        def empty_resize_pipe():
            # clean out the pipe used to signal external event loops
            # that a resize has occured
            try:
                while True: os.read(self._resize_pipe_rd, 1)
            except OSError:
                pass

        while True:
            processed = []
            codes = self._get_gpm_codes() + \
                self._get_keyboard_codes()

            original_codes = codes
            try:
                while codes:
                    run, codes = escape.process_keyqueue(
                        codes, True)
                    processed.extend(run)
            except escape.MoreInputRequired:
                k = len(original_codes) - len(codes)
                yield (self.complete_wait, processed,
                    original_codes[:k])
                empty_resize_pipe()
                original_codes = codes
                processed = []

                codes += self._get_keyboard_codes() + \
                    self._get_gpm_codes()
                while codes:
                    run, codes = escape.process_keyqueue(
                        codes, False)
                    processed.extend(run)
            
            if self._resized:
                processed.append('window resize')
                self._resized = False

            yield (self.max_wait, processed, original_codes)
            empty_resize_pipe()

    def _fake_input_iter(self):
        """
        This generator is a placeholder for when the screen is stopped
        to always return that no input is available.
        """
        while True:
            yield (self.max_wait, [], [])

    def _get_keyboard_codes(self):
        codes = []
        while True:
            code = self._getch_nodelay()
            if code < 0:
                break
            codes.append(code)
        return codes

    def _get_gpm_codes(self):
        codes = []
        try:
            while self.gpm_mev is not None and self.gpm_event_pending:
                codes.extend(self._encode_gpm_event())
        except IOError, e:
            if e.args[0] != 11:
                raise
        return codes

    def _wait_for_input_ready(self, timeout):
        ready = None
        fd_list = [self._term_input_file.fileno()]
        if self.gpm_mev is not None:
            fd_list.append(self.gpm_mev.stdout.fileno())
        while True:
            try:
                if timeout is None:
                    ready,w,err = select.select(
                        fd_list, [], fd_list)
                else:
                    ready,w,err = select.select(
                        fd_list,[],fd_list, timeout)
                break
            except select.error, e:
                if e.args[0] != 4: 
                    raise
                if self._resized:
                    ready = []
                    break
        return ready    
        
    def _getch(self, timeout):
        ready = self._wait_for_input_ready(timeout)
        if self.gpm_mev is not None:
            if self.gpm_mev.stdout.fileno() in ready:
                self.gpm_event_pending = True
        if self._term_input_file.fileno() in ready:
            return ord(os.read(self._term_input_file.fileno(), 1))
        return -1
    
    def _encode_gpm_event( self ):
        self.gpm_event_pending = False
        s = self.gpm_mev.stdout.readline().decode('ascii')
        l = s.split(",")
        if len(l) != 6:
            # unexpected output, stop tracking
            self._stop_gpm_tracking()
            signals.emit_signal(self, INPUT_DESCRIPTORS_CHANGED)
            return []
        ev, x, y, ign, b, m = s.split(",")
        ev = int( ev.split("x")[-1], 16)
        x = int( x.split(" ")[-1] )
        y = int( y.lstrip().split(" ")[0] )
        b = int( b.split(" ")[-1] )
        m = int( m.split("x")[-1].rstrip(), 16 )

        # convert to xterm-like escape sequence

        last = next = self.last_bstate
        l = []
        
        mod = 0
        if m & 1:    mod |= 4 # shift
        if m & 10:    mod |= 8 # alt
        if m & 4:    mod |= 16 # ctrl

        def append_button( b ):
            b |= mod
            l.extend([ 27, ord('['), ord('M'), b+32, x+32, y+32 ])

        if ev == 20: # press
            if b & 4 and last & 1 == 0:
                append_button( 0 )
                next |= 1
            if b & 2 and last & 2 == 0:
                append_button( 1 )
                next |= 2
            if b & 1 and last & 4 == 0:
                append_button( 2 )
                next |= 4
        elif ev == 146: # drag
            if b & 4:
                append_button( 0 + escape.MOUSE_DRAG_FLAG )
            elif b & 2:
                append_button( 1 + escape.MOUSE_DRAG_FLAG )
            elif b & 1:
                append_button( 2 + escape.MOUSE_DRAG_FLAG )
        else: # release
            if b & 4 and last & 1:
                append_button( 0 + escape.MOUSE_RELEASE_FLAG )
                next &= ~ 1
            if b & 2 and last & 2:
                append_button( 1 + escape.MOUSE_RELEASE_FLAG )
                next &= ~ 2
            if b & 1 and last & 4:
                append_button( 2 + escape.MOUSE_RELEASE_FLAG )
                next &= ~ 4
            
        self.last_bstate = next
        return l
    
    def _getch_nodelay(self):
        return self._getch(0)
    
    
    def get_cols_rows(self):
        """Return the terminal dimensions (num columns, num rows)."""
        buf = fcntl.ioctl(0, termios.TIOCGWINSZ, ' '*4)
        y, x = struct.unpack('hh', buf)
        self.maxrow = y
        return x, y

    def _setup_G1(self):
        """
        Initialize the G1 character set to graphics mode if required.
        """
        if self._setup_G1_done:
            return
        
        while True:
            try:
                self._term_output_file.write(escape.DESIGNATE_G1_SPECIAL)
                self._term_output_file.flush()
                break
            except IOError:
                pass
        self._setup_G1_done = True

    
    def draw_screen(self, (maxcol, maxrow), r ):
        """Paint screen with rendered canvas."""
        assert self._started

        assert maxrow == r.rows()

        # quick return if nothing has changed
        if self.screen_buf and r is self._screen_buf_canvas:
            return

        self._setup_G1()
        
        if self._resized: 
            # handle resize before trying to draw screen
            return
        
        o = [escape.HIDE_CURSOR, self._attrspec_to_escape(AttrSpec('',''))]
        
        def partial_display():
            # returns True if the screen is in partial display mode
            # ie. only some rows belong to the display
            return self._rows_used is not None

        if not partial_display():
            o.append(escape.CURSOR_HOME)

        if self.screen_buf:
            osb = self.screen_buf
        else:
            osb = []
        sb = []
        cy = self._cy
        y = -1

        def set_cursor_home():
            if not partial_display():
                return escape.set_cursor_position(0, 0)
            return (escape.CURSOR_HOME_COL + 
                escape.move_cursor_up(cy))
        
        def set_cursor_row(y):
            if not partial_display():
                return escape.set_cursor_position(0, y)
            return escape.move_cursor_down(y - cy)

        def set_cursor_position(x, y):
            if not partial_display():
                return escape.set_cursor_position(x, y)
            if cy > y:
                return ('\b' + escape.CURSOR_HOME_COL +
                    escape.move_cursor_up(cy - y) +
                    escape.move_cursor_right(x))
            return ('\b' + escape.CURSOR_HOME_COL +
                escape.move_cursor_down(y - cy) +
                escape.move_cursor_right(x))
        
        def is_blank_row(row):
            if len(row) > 1:
                return False
            if row[0][2].strip():
                return False
            return True

        def attr_to_escape(a):
            if a in self._pal_escape:
                return self._pal_escape[a]
            elif isinstance(a, AttrSpec):
                return self._attrspec_to_escape(a)
            # undefined attributes use default/default
            # TODO: track and report these
            return self._attrspec_to_escape(
                AttrSpec('default','default'))

        ins = None
        o.append(set_cursor_home())
        cy = 0
        for row in r.content():
            y += 1
            if False and osb and osb[y] == row:
                # this row of the screen buffer matches what is
                # currently displayed, so we can skip this line
                sb.append( osb[y] )
                continue

            sb.append(row)

            # leave blank lines off display when we are using
            # the default screen buffer (allows partial screen)
            if partial_display() and y > self._rows_used:
                if is_blank_row(row):
                    continue
                self._rows_used = y

            if y or partial_display():
                o.append(set_cursor_position(0, y))
            # after updating the line we will be just over the
            # edge, but terminals still treat this as being
            # on the same line
            cy = y

            whitespace_at_end = False
            if row and row[-1][2][-1:] == B(' '):
                whitespace_at_end = True
                a, cs, run = row[-1]
                row = row[:-1] + [(a, cs, run.rstrip(B(' ')))]
            elif y == maxrow-1 and maxcol>1:
                row, back, ins = self._last_row(row)

            first = True
            lasta = lastcs = None
            for (a,cs, run) in row:
                assert isinstance(run, bytes) # canvases should render with bytes
                if cs != 'U':
                    run = run.translate(UNPRINTABLE_TRANS_TABLE)
                if first or lasta != a:
                    o.append(attr_to_escape(a))
                    lasta = a
                if first or lastcs != cs:
                    assert cs in [None, "0", "U"], repr(cs)
                    if lastcs == "U":
                        o.append( escape.IBMPC_OFF )

                    if cs is None:
                        o.append( escape.SI )
                    elif cs == "U":
                        o.append( escape.IBMPC_ON )
                    else:
                        o.append( escape.SO )
                    lastcs = cs
                o.append( run )
                first = False
            if ins:
                (inserta, insertcs, inserttext) = ins
                ias = attr_to_escape(inserta)
                assert insertcs in [None, "0", "U"], repr(insertcs)
                if cs is None:
                    icss = escape.SI
                elif cs == "U":
                    icss = escape.IBMPC_ON
                else:
                    icss = escape.SO
                o += [    "\x08"*back, 
                    ias, icss,
                    escape.INSERT_ON, inserttext,
                    escape.INSERT_OFF ]

                if cs == "U":
                    o.append(escape.IBMPC_OFF)
            if whitespace_at_end:
                o.append(escape.ERASE_IN_LINE_RIGHT)

        if r.cursor is not None:
            x,y = r.cursor
            o += [set_cursor_position(x, y),
                escape.SHOW_CURSOR  ]
            self._cy = y

        if self._resized:
            # handle resize before trying to draw screen
            return
        try:
            for l in o:
                if isinstance(l, bytes) and PYTHON3:
                    l = l.decode('utf-8')
                self._term_output_file.write(l)
            self._term_output_file.flush()
        except IOError, e:
            # ignore interrupted syscall
            if e.args[0] != 4:
                raise

        self.screen_buf = sb
        self._screen_buf_canvas = r


    def _last_row(self, row):
        """On the last row we need to slide the bottom right character
        into place. Calculate the new line, attr and an insert sequence
        to do that.

        eg. last row:
        XXXXXXXXXXXXXXXXXXXXYZ

        Y will be drawn after Z, shifting Z into position.
        """

        new_row = row[:-1]
        z_attr, z_cs, last_text = row[-1]
        last_cols = util.calc_width(last_text, 0, len(last_text))
        last_offs, z_col = util.calc_text_pos(last_text, 0, 
            len(last_text), last_cols-1)
        if last_offs == 0:
            z_text = last_text
            del new_row[-1]
            # we need another segment
            y_attr, y_cs, nlast_text = row[-2]
            nlast_cols = util.calc_width(nlast_text, 0, 
                len(nlast_text))
            z_col += nlast_cols
            nlast_offs, y_col = util.calc_text_pos(nlast_text, 0,
                len(nlast_text), nlast_cols-1)
            y_text = nlast_text[nlast_offs:]
            if nlast_offs:
                new_row.append((y_attr, y_cs, 
                    nlast_text[:nlast_offs]))
        else:
            z_text = last_text[last_offs:]
            y_attr, y_cs = z_attr, z_cs
            nlast_cols = util.calc_width(last_text, 0,
                last_offs)
            nlast_offs, y_col = util.calc_text_pos(last_text, 0,
                last_offs, nlast_cols-1)
            y_text = last_text[nlast_offs:last_offs]
            if nlast_offs:
                new_row.append((y_attr, y_cs,
                    last_text[:nlast_offs]))
        
        new_row.append((z_attr, z_cs, z_text))
        return new_row, z_col-y_col, (y_attr, y_cs, y_text)

            
    
    def clear(self):
        """
        Force the screen to be completely repainted on the next
        call to draw_screen().
        """
        self.screen_buf = None
        self.setup_G1 = True

        
    def _attrspec_to_escape(self, a):
        """
        Convert AttrSpec instance a to an escape sequence for the terminal

        >>> s = Screen()
        >>> s.set_terminal_properties(colors=256)
        >>> a2e = s._attrspec_to_escape
        >>> a2e(s.AttrSpec('brown', 'dark green'))
        '\\x1b[0;33;42m'
        >>> a2e(s.AttrSpec('#fea,underline', '#d0d'))
        '\\x1b[0;38;5;229;4;48;5;164m'
        """
        if a.foreground_high:
            fg = "38;5;%d" % a.foreground_number
        elif a.foreground_basic:
            if a.foreground_number > 7:
                if self.bright_is_bold:
                    fg = "1;%d" % (a.foreground_number - 8 + 30)
                else:
                    fg = "%d" % (a.foreground_number - 8 + 90)
            else:
                fg = "%d" % (a.foreground_number + 30)
        else:
            fg = "39"
        st = ("1;" * a.bold + "4;" * a.underline +
              "5;" * a.blink + "7;" * a.standout)
        if a.background_high:
            bg = "48;5;%d" % a.background_number
        elif a.background_basic:
            if a.background_number > 7:
                # this doesn't work on most terminals
                bg = "%d" % (a.background_number - 8 + 100)
            else:
                bg = "%d" % (a.background_number + 40)
        else:
            bg = "49"
        return escape.ESC + "[0;%s;%s%sm" % (fg, st, bg)


    def set_terminal_properties(self, colors=None, bright_is_bold=None,
        has_underline=None):
        """
        colors -- number of colors terminal supports (1, 16, 88 or 256)
            or None to leave unchanged
        bright_is_bold -- set to True if this terminal uses the bold 
            setting to create bright colors (numbers 8-15), set to False
            if this Terminal can create bright colors without bold or
            None to leave unchanged
        has_underline -- set to True if this terminal can use the
            underline setting, False if it cannot or None to leave
            unchanged
        """
        if colors is None:
            colors = self.colors
        if bright_is_bold is None:
            bright_is_bold = self.bright_is_bold
        if has_underline is None:
            has_underline = self.has_underline

        if colors == self.colors and bright_is_bold == self.bright_is_bold \
            and has_underline == self.has_underline:
            return

        self.colors = colors
        self.bright_is_bold = bright_is_bold
        self.has_underline = has_underline
            
        self.clear()
        self._pal_escape = {}
        for p,v in self._palette.items():
            self._on_update_palette_entry(p, *v)



    def reset_default_terminal_palette(self):
        """
        Attempt to set the terminal palette to default values as taken
        from xterm.  Uses number of colors from current 
        set_terminal_properties() screen setting.
        """
        if self.colors == 1:
            return

        def rgb_values(n):
            if self.colors == 16:
                aspec = AttrSpec("h%d"%n, "", 256)
            else:
                aspec = AttrSpec("h%d"%n, "", self.colors)
            return aspec.get_rgb_values()[:3]

        entries = [(n,) + rgb_values(n) for n in range(self.colors)]
        self.modify_terminal_palette(entries)


    def modify_terminal_palette(self, entries):
        """
        entries - list of (index, red, green, blue) tuples.

        Attempt to set part of the terminal pallette (this does not work
        on all terminals.)  The changes are sent as a single escape
        sequence so they should all take effect at the same time.
        
        0 <= index < 256 (some terminals will only have 16 or 88 colors)
        0 <= red, green, blue < 256
        """

        modify = ["%d;rgb:%02x/%02x/%02x" % (index, red, green, blue)
            for index, red, green, blue in entries]
        self._term_output_file.write("\x1b]4;"+";".join(modify)+"\x1b\\")
        self._term_output_file.flush()


    # shortcut for creating an AttrSpec with this screen object's
    # number of colors
    AttrSpec = lambda self, fg, bg: AttrSpec(fg, bg, self.colors)
    

def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()
