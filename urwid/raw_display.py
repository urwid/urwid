#!/usr/bin/python
#
# Urwid raw display module
#    Copyright (C) 2004-2006  Ian Ward
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

from __future__ import nested_scopes

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

try: True # old python?
except: False, True = 0, 1


# replace control characters with ?'s
_trans_table = "?"*32+"".join([chr(x) for x in range(32,256)])


class Screen:
	def __init__(self):
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

	def set_input_timeouts(self, max_wait=0.5, complete_wait=0.1, 
		resize_wait=0.1):
		"""
		Set the get_input timeout values.  All values have are floating
		point number of seconds.
		
		max_wait -- amount of time in seconds to wait for input when
			there is no input pending
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
	
	def run_wrapper(self,fn):
		""" Call fn and reset terminal on exit.
		"""
		old_settings = termios.tcgetattr(0)
		try:
			self.signal_init()
			tty.setcbreak(sys.stdin.fileno())
			return fn()
		finally:
			self.signal_restore()
			termios.tcsetattr(0, termios.TCSADRAIN, old_settings)
			move_cursor = ""
			if self.gpm_mev:
				self._stop_gpm_tracking()
			if self.maxrow is not None:
				move_cursor = escape.set_cursor_position( 
					0, self.maxrow)
			sys.stdout.write( escape.set_attributes( 
				'default', 'default') 
				+ escape.SI
				+ escape.MOUSE_TRACKING_OFF
				+ move_cursor + "\n" + escape.SHOW_CURSOR )
			
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
		
		keys, raw = self._get_input( self.max_wait )
		
		# Avoid pegging CPU at 100% when slowly resizing
		if keys==['window resize'] and self.prev_input_resize:
			while True:
				keys, raw2 = self._get_input(self.resize_wait)
				raw += raw2
				if not keys:
					keys, raw2 = self._get_input( 
						self.resize_wait)
					raw += raw2
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
		
	
	def _get_input(self, timeout):	
		key = self._getch(timeout)
		raw = []
		keys = []
		
		while key >= 0 or self.gpm_event_pending:
			if self.gpm_event_pending:
				keys += self._encode_gpm_event()

			if key >= 0:
				raw.append(key)
				keys.append(key)
			key = self._getch_nodelay()

		processed = []
		
		
		def more_fn(raw=raw,
				# hide warnings in python 2.1
				self_getch=self._getch, 
				self_complete_wait = self.complete_wait):
			key = self_getch(self_complete_wait)
			if key >= 0:
				raw.append(key)
			return key
			
		while keys:
			run, keys = escape.process_keyqueue(keys, more_fn)
			processed += run

		if self.resized:
			processed.append('window resize')
			self.resized = False
			self.screen_buf = None

		return processed, raw
		
	def _getch(self, timeout):
		ready = None
		fd_list = [0]
		if self.gpm_mev is not None:
			fd_list += [ self.gpm_mev.fromchild ]
		while True:
			try:
				ready,w,err = select.select(
					fd_list,[],fd_list, timeout)
				break
			except select.error, e:
				if e.args[0] != 4: 
					raise
				if self.resized:
					ready = []
					break
		if self.gpm_mev is not None:
			if self.gpm_mev.fromchild in ready:
				self.gpm_event_pending = True
		if 0 in ready:
			return ord(os.read(0, 1))
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

		if self.setup_G1:
			try:
				if util._use_dec_special:
					sys.stdout.write(
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

		lines = r.text
		line = r.text
		ins = None
		cy = 0
		for y in range(len(lines)):
			line = lines[y].translate( _trans_table )
			attr_cs = util.rle_product(r.attr[y], r.cs[y])
			
			if osb and osb[y] == (line, attr_cs):
				sb.append( osb[y] )
				continue
			sb.append( (line, attr_cs) )
			
			if cy != y:  
				o.append( escape.set_cursor_position(0,y) )
			cy = y+1 # will be here after updating this line
			
			if y == maxrow-1:
				line, attr_cs, ins = self._last_row(
					maxcol, line, attr_cs)

			col = 0
			first = True
			lasta = lastcs = None
			for (a,cs), run in attr_cs:
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
				o.append( line[col:col+run] )
				col += run
				first = False
			if ins:
				insert, (inserta, insertcs), back = ins
				ias = self.palette[inserta][0]
				assert insertcs in [None, "0"], `insertcs`
				if cs is None:
					icss = escape.SI
				else:
					icss = escape.SO
				o += [	"\x08"*back, 
					ias, icss,
					escape.INSERT_ON, insert,
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
				
	
	def _last_row(self, maxcol, line, attr_cs):
		"""On the last row we need to slide the bottom right character
		into place. Calculate the new line, attr and an insert sequence
		to do that."""
		
		ll = len(line)
		if ll == 0:
			return line, attr, None
		# offset of last position
		i1, p1 = util.calc_text_pos( line, 0, ll, maxcol-1 )
		if i1 == 0:
			return line, attr, None
		# offset of next-to-last position
		i2, p2 = util.calc_text_pos( line, 0, ll, p1-1 )

		insert = line[i2:i1] # we will insert this range
		inserta_cs = util.rle_subseg(attr_cs,i2,i1)[0][0]

		attr_cs = util.rle_subseg(attr_cs, 0, i2) + util.rle_subseg(
			attr_cs, i1, ll)
		line = line[0:i2] + line[i1:]
		back = maxcol-p1
		
		return line, attr_cs, (insert, inserta_cs, back)
			
	
	def clear(self):
		"""
		Force the screen to be completely repainted on the next
		call to draw_screen().
		"""
		self.screen_buf = None
		self.setup_G1 = True
		
