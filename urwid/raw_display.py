#!/usr/bin/python
#
# Urwid raw display module
#    Copyright (C) 2004-2007  Ian Ward
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
import popen2

import util
import escape


# replace control characters with ?'s
_trans_table = "?"*32+"".join([chr(x) for x in range(32,256)])


class RealTerminal(object):
	def __init__(self):
		super(RealTerminal,self).__init__()
		self._signal_keys_set = False
		self._old_signal_keys = None
		
	def tty_signal_keys(self, intr=None, quit=None, start=None, 
		stop=None, susp=None):
		"""
		Read and/or set the tty's signal charater settings.
		This function returns the current settings as a tuple.

		Use the string 'undefined' to unmap keys from their signals.
		The value None is used when no change is being made.
		Setting signal keys is done using the integer ascii
		code for the key, eg.  3 for CTRL+C.

		If this function is called after start() has been called
		then the original settings will be restored when stop()
		is called.
		"""
		fd = sys.stdin.fileno()
		tattr = termios.tcgetattr(fd)
		sattr = tattr[6]
		skeys = (sattr[termios.VINTR], sattr[termios.VQUIT],
			sattr[termios.VSTART], sattr[termios.VSTOP],
			sattr[termios.VSUSP])
		
		if intr == 'undefined': intr = 0
		if quit == 'undefined': quit = 0
		if start == 'undefined': start = 0
		if stop == 'undefined': stop = 0
		if susp == 'undefined': susp = 0
		
		if intr is not None: tattr[6][termios.VINTR] = intr
		if quit is not None: tattr[6][termios.VQUIT] = quit
		if start is not None: tattr[6][termios.VSTART] = start
		if stop is not None: tattr[6][termios.VSTOP] = stop
		if susp is not None: tattr[6][termios.VSUSP] = susp
		
		if intr is not None or quit is not None or \
			start is not None or stop is not None or \
			susp is not None:
			termios.tcsetattr(fd, termios.TCSADRAIN, tattr)
			self._signal_keys_set = True
		
		return skeys
      


class Screen(RealTerminal):
	def __init__(self):
		super(Screen, self).__init__()
		self.palette = {}
		self.register_palette_entry( None, 'default','default')
		self.has_color = True # FIXME: detect this
		self._keyqueue = []
		self.prev_input_resize = 0
		self.set_input_timeouts()
		self.screen_buf = None
		self.resized = False
		self.maxrow = None
		self.gpm_mev = None
		self.gpm_event_pending = False
		self.last_bstate = 0
		self.setup_G1 = True
		self._started = False
	
	started = property(lambda self: self._started)

	def register_palette( self, l ):
		"""Register a list of palette entries.

		l -- list of (name, foreground, background, mono),
		     (name, foreground, background) or
		     (name, same_as_other_name) palette entries.

		calls self.register_palette_entry for each item in l
		"""
		
		for item in l:
			if len(item) in (3,4):
				self.register_palette_entry( *item )
				continue
			assert len(item) == 2, "Invalid register_palette usage"
			name, like_name = item
			if not self.palette.has_key(like_name):
				raise Exception("palette entry '%s' doesn't exist"%like_name)
			self.palette[name] = self.palette[like_name]

	def register_palette_entry( self, name, foreground, background,
		mono=None):
		"""Register a single palette entry.

		name -- new entry/attribute name
		foreground -- foreground colour, one of: 'black', 'dark red',
			'dark green', 'brown', 'dark blue', 'dark magenta',
			'dark cyan', 'light gray', 'dark gray', 'light red',
			'light green', 'yellow', 'light blue', 'light magenta',
			'light cyan', 'white', 'default' (black if unable to
			use terminal's default)
		background -- background colour, one of: 'black', 'dark red',
			'dark green', 'brown', 'dark blue', 'dark magenta',
			'dark cyan', 'light gray', 'default' (light gray if
			unable to use terminal's default)
		mono -- monochrome terminal attribute, one of: None (default),
			'bold',	'underline', 'standout', or a tuple containing
			a combination eg. ('bold','underline')
			
		"""
		assert (mono is None or 
			mono in (None, 'bold', 'underline', 'standout') or
			type(mono)==type(()))
		
		self.palette[name] = (escape.set_attributes(
			foreground, background), mono)

	def set_input_timeouts(self, max_wait=None, complete_wait=0.1, 
		resize_wait=0.1):
		"""
		Set the get_input timeout values.  All values have are floating
		point number of seconds.
		
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
		self.complete_wait = complete_wait
		self.resize_wait = resize_wait

	def _sigwinch_handler(self, signum, frame):
		self.resized = True
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
		sys.stdout.write(escape.MOUSE_TRACKING_ON)

		self._start_gpm_tracking()
	
	def _start_gpm_tracking(self):
		if not os.path.isfile("/usr/bin/mev"):
			return
		if not os.environ.get('TERM',"").lower().startswith("linux"):
			return
		m = popen2.Popen3("/usr/bin/mev -e 158")
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
			sys.stdout.write(escape.SWITCH_TO_ALTERNATE_BUFFER)
		self._old_termios_settings = termios.tcgetattr(0)
		self.signal_init()
		tty.setcbreak(sys.stdin.fileno())
		self._alternate_buffer = alternate_buffer
		self._input_iter = self._run_input_iter()
		self._next_timeout = self.max_wait
		
		if not self._signal_keys_set:
			self._old_signal_keys = self.tty_signal_keys()

		self._started = True

	
	def stop(self):
		"""
		Restore the screen.
		"""
		self.clear()
		if not self._started:
			return
		self.signal_restore()
		termios.tcsetattr(0, termios.TCSADRAIN, 
			self._old_termios_settings)
		move_cursor = ""
		if self.gpm_mev:
			self._stop_gpm_tracking()
		if self._alternate_buffer:
			move_cursor = escape.RESTORE_NORMAL_BUFFER
		elif self.maxrow is not None:
			move_cursor = escape.set_cursor_position( 
				0, self.maxrow)
		sys.stdout.write( escape.set_attributes( 
			'default', 'default') 
			+ escape.SI
			+ escape.MOUSE_TRACKING_OFF
			+ escape.SHOW_CURSOR
			+ move_cursor + "\n" + escape.SHOW_CURSOR )
		self._input_iter = None

		if self._old_signal_keys:
			self.tty_signal_keys(*self._old_signal_keys)
		
		self._started = False
		

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
		
		Examples of keys returned
		-------------------------
		ASCII printable characters:  " ", "a", "0", "A", "-", "/" 
		ASCII control characters:  "tab", "enter"
		Escape sequences:  "up", "page up", "home", "insert", "f1"
		Key combinations:  "shift f1", "meta a", "ctrl b"
		Window events:  "window resize"
		
		When a narrow encoding is not enabled
		"Extended ASCII" characters:  "\\xa1", "\\xb2", "\\xfe"

		When a wide encoding is enabled
		Double-byte characters:  "\\xa1\\xea", "\\xb2\\xd4"

		When utf8 encoding is enabled
		Unicode characters: u"\\u00a5", u'\\u253c"
		
		Examples of mouse events returned
		---------------------------------
		Mouse button press: ('mouse press', 1, 15, 13), 
		                    ('meta mouse press', 2, 17, 23)
		Mouse drag: ('mouse drag', 1, 16, 13),
		            ('mouse drag', 1, 17, 13),
			    ('ctrl mouse drag', 1, 18, 13)
		Mouse button release: ('mouse release', 0, 18, 13),
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
				#	keys, raw2 = self._get_input( 
				#		self.resize_wait)
				#	raw += raw2
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
		fd_list = [sys.stdin.fileno()]
		if self.gpm_mev is not None:
			fd_list.append(self.gpm_mev.fromchild.fileno())
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
		assert self._started

		return self._input_iter.next()

	def _run_input_iter(self):
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
				original_codes = codes
				processed = []

				codes += self._get_keyboard_codes() + \
					self._get_gpm_codes()
				while codes:
					run, codes = escape.process_keyqueue(
						codes, False)
					processed.extend(run)
			
			if self.resized:
				processed.append('window resize')
				self.resized = False

			yield (self.max_wait, processed, original_codes)

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
		while self.gpm_event_pending:
			codes.extend(self._encode_gpm_event())
		return codes

	def _wait_for_input_ready(self, timeout):
		ready = None
		fd_list = [sys.stdin.fileno()]
		if self.gpm_mev is not None:
			fd_list += [ self.gpm_mev.fromchild ]
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
				if self.resized:
					ready = []
					break
		return ready	
		
	def _getch(self, timeout):
		ready = self._wait_for_input_ready(timeout)
		if self.gpm_mev is not None:
			if self.gpm_mev.fromchild.fileno() in ready:
				self.gpm_event_pending = True
		if sys.stdin.fileno() in ready:
			return ord(os.read(sys.stdin.fileno(), 1))
		return -1
	
	def _encode_gpm_event( self ):
		self.gpm_event_pending = False
		s = self.gpm_mev.fromchild.readline()
		l = s.split(",")
		if len(l) != 6:
			# unexpected output, stop tracking
			self._stop_gpm_tracking()
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
		if m & 1:	mod |= 4 # shift
		if m & 10:	mod |= 8 # alt
		if m & 4:	mod |= 16 # ctrl

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
	
	def draw_screen(self, (maxcol, maxrow), r ):
		"""Paint screen with rendered canvas."""
		assert self._started

		assert maxrow == r.rows()

		if self.setup_G1:
			try:
				if util._use_dec_special:
					sys.stdout.write(
						escape.CURSOR_HOME +
						escape.DESIGNATE_G1_SPECIAL)
					sys.stdout.flush()
				self.setup_G1 = False
			except IOError, e:
				pass
		
		if self.resized: 
			# handle resize before trying to draw screen
			return
		
		o = [	escape.HIDE_CURSOR, escape.CURSOR_HOME, 
			escape.set_attributes('default','default') ]
		
		if self.screen_buf:
			osb = self.screen_buf
		else:
			osb = []
		sb = []

		ins = None
		#cy = 0
		y = -1
		for row in r.content():
			y += 1
			if osb and osb[y] == row:
				sb.append( osb[y] )
				continue
			sb.append(row)
			
			#if cy != y:  
			o.append( escape.set_cursor_position(0,y) )
			#cy = y+1 # will be here after updating this line
			
			if y == maxrow-1:
				row, back, ins = self._last_row(row)

			first = True
			lasta = lastcs = None
			for (a,cs, run) in row:
				run = run.translate( _trans_table )
				assert self.palette.has_key(a), `a`
				if first or lasta != a:
					o.append( self.palette[a][0] )
					lasta = a
				if first or lastcs != cs:
					assert cs in [None, "0"], `cs`
					if cs is None:
						o.append( escape.SI )
					else:
						o.append( escape.SO )
					lastcs = cs
				o.append( run )
				first = False
			if ins:
				(inserta, insertcs, inserttext) = ins
				ias = self.palette[inserta][0]
				assert insertcs in [None, "0"], `insertcs`
				if cs is None:
					icss = escape.SI
				else:
					icss = escape.SO
				o += [	"\x08"*back, 
					ias, icss,
					escape.INSERT_ON, inserttext,
					escape.INSERT_OFF ]

		if r.cursor is not None:
			x,y = r.cursor
			o += [  escape.set_cursor_position( x, y ), 
				escape.SHOW_CURSOR  ]
		
		if self.resized: 
			# handle resize before trying to draw screen
			return
		try:
			k = 0
			for l in o:
				sys.stdout.write( l )
				k += len(l)
				if k > 100:
					sys.stdout.flush()
					k = 0
			sys.stdout.flush()
		except IOError, e:
			# ignore interrupted syscall
			if e.args[0] != 4:
				raise

		self.screen_buf = sb
		self.keep_cache_alive_link = r
				
	
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
		
