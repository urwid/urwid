#!/usr/bin/python
#
# Urwid curses output wrapper.. the horror..
#    Copyright (C) 2004-2005  Ian Ward
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
Curses-based UI implementation
"""

import curses
import sys

import util

try: True # old python?
except: False, True = 0, 1
		

_curses_colours = {
	'default':		(-1,			0),
	'black':		(curses.COLOR_BLACK,	0),
	'dark red':		(curses.COLOR_RED,	0),
	'dark green':		(curses.COLOR_GREEN,	0),
	'brown':		(curses.COLOR_YELLOW,	0),
	'dark blue':		(curses.COLOR_BLUE,	0),
	'dark magenta':		(curses.COLOR_MAGENTA,	0),
	'dark cyan':		(curses.COLOR_CYAN,	0),
	'light gray':		(curses.COLOR_WHITE,	0),
	'dark gray':		(curses.COLOR_BLACK,    1),
	'light red':		(curses.COLOR_RED,      1),
	'light green':		(curses.COLOR_GREEN,    1),
	'yellow':		(curses.COLOR_YELLOW,   1),
	'light blue':		(curses.COLOR_BLUE,     1),
	'light magenta':	(curses.COLOR_MAGENTA,  1),
	'light cyan':		(curses.COLOR_CYAN,     1),
	'white':		(curses.COLOR_WHITE,	1),
}

_keyconv = {
	8:'backspace',
	9:'tab',
	10:'enter',
	127:'backspace',
	258:'down',
	259:'up',
	260:'left',
	261:'right',
	262:'home',
	263:'backspace',
	265:'f1', 266:'f2', 267:'f3', 268:'f4',
	269:'f5', 270:'f6', 271:'f7', 272:'f8',
	273:'f9', 274:'f10', 275:'f11', 276:'f12',
	277:'shift f1', 278:'shift f2', 279:'shift f3', 280:'shift f4',
	281:'shift f5', 282:'shift f6', 283:'shift f7', 284:'shift f8',
	285:'shift f9', 286:'shift f10', 287:'shift f11', 288:'shift f12',
	330:'delete',
	331:'insert',
	338:'page down',
	339:'page up',
	343:'enter',    # on numpad
	350:'5',        # on numpad
	360:'end',
	 -1:None,
}

def escape_modifier( digit ):
	mode = ord(digit) - ord("1")
	return "shift "*(mode&1) + "meta "*((mode&2)/2) + "ctrl "*((mode&4)/4)
	

_escape_sequences = [
	('[A','up'),('[B','down'),('[C','right'),('[D','left'),
	('[E','5'),('[F','end'),('[G','5'),('[H','home'),

	('[1~','home'),('[2~','insert'),('[3~','delete'),('[4~','end'),
	('[5~','page up'),('[6~','page down'),

	('[[A','f1'),('[[B','f2'),('[[C','f3'),('[[D','f4'),('[[E','f5'),
	
	('[11~','f1'),('[12~','f2'),('[13~','f3'),('[14~','f4'),
	('[15~','f5'),('[17~','f6'),('[18~','f7'),('[19~','f8'),
	('[20~','f9'),('[21~','f10'),('[23~','f11'),('[24~','f12'),
	('[25~','f13'),('[26~','f14'),('[28~','f15'),('[29~','f16'),
	('[31~','f17'),('[32~','f18'),('[33~','f19'),('[34~','f20'),

	('OA','up'),('OB','down'),('OC','right'),('OD','left'),
	('OH','home'),('OF','end'),
	('OP','f1'),('OQ','f2'),('OR','f3'),('OS','f4'),
	('Oo','/'),('Oj','*'),('Om','-'),('Ok','+'),

	('[Z','shift tab'),
] + [ 
	# modified cursor keys + home, end, 5 -- [#X and [1;#X forms
	(prefix+digit+letter, escape_modifier(digit) + key)
	for prefix in "[","[1;"
	for digit in "12345678"
	for letter,key in zip("ABCDEFGH",
		('up','down','right','left','5','end','5','home'))
] + [ 
	# modified F1-F4 keys -- O#X form
	("O"+digit+letter, escape_modifier(digit) + key)
	for digit in "12345678"
	for letter,key in zip("PQRS",('f1','f2','f3','f4'))
] + [ 
	# modified F1-F13 keys -- [XX;#~ form
	("["+str(num)+";"+digit+"~", escape_modifier(digit) + key)
	for digit in "12345678"
	for num,key in zip(
		(11,12,13,14,15,17,18,19,20,21,23,24,25,26,28,29,31,32,33,34),
		('f1','f2','f3','f4','f5','f6','f7','f8','f9','f10','f11',
		'f12','f13','f14','f15','f16','f17','f18','f19','f20'))
]

class _KeyqueueTrie:
	def __init__( self, sequences ):
		self.data = {}
		for s, result in sequences:
			assert type(result) != type({})
			self.add(self.data, s, result)
	
	def add(self, root, s, result):
		assert type(root) == type({}), "trie conflict detected"
		assert len(s) > 0, "trie conflict detected"
		
		if root.has_key(ord(s[0])):
			return self.add(root[ord(s[0])], s[1:], result)
		if len(s)>1:
			d = {}
			root[ord(s[0])] = d
			return self.add(d, s[1:], result)
		root[ord(s)] = result
	
	def get(self, keys, more_fn):
		return self.get_recurse(self.data, keys, more_fn)
	
	def get_recurse(self, root, keys, more_fn):
		if type(root) != type({}):
			return (root, keys)
		if not keys:
			# get more keys
			key = more_fn()
			if key < 0:
				return None
			keys.append(key)
		if not root.has_key(keys[0]):
			return None
		return self.get_recurse( root[keys[0]], keys[1:], more_fn )
		

_escape_trie = _KeyqueueTrie(_escape_sequences)


# replace control characters with ?'s
_trans_table = "?"*32+"".join([chr(x) for x in range(32,256)])

WINDOW_RESIZE = 410

class Screen:
	def __init__(self):
		self.curses_pairs = [
			(None,None), # Can't be sure what pair 0 will default to
		]
		self.palette = {}
		self.has_color = False
		self.s = None
		self.cursor_state = None
		self._keyqueue = []
		self.prev_input_resize = 0
		self.set_input_timeouts()

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
		fg_a, fg_b = _curses_colours[foreground]
		bg_a, bg_b = _curses_colours[background]
		if bg_b: # can't do bold backgrounds
			raise Exception("%s is not a supported background colour"%background )
		assert (mono is None or 
			mono in (None, 'bold', 'underline', 'standout') or
			type(mono)==type(()))
	
		for i in range(len(self.curses_pairs)):
			pair = self.curses_pairs[i]
			if pair == (fg_a, bg_a): break
		else:
			i = len(self.curses_pairs)
			self.curses_pairs.append( (fg_a, bg_a) )
		
		self.palette[name] = (i, fg_b, mono)
		
	
	def run_wrapper(self,fn):
		"""Call fn in fullscreen mode.  Return to normal on exit.
		
		This function should be called to wrap your main program loop.
		Exception tracebacks will be displayed in normal mode.
		"""
	
		self.s = curses.initscr()
		try:
			self.has_color = curses.has_colors()
			if self.has_color:
				curses.start_color()
				if curses.COLORS < 8:
					# not colourful enough
					self.has_color = False
			if self.has_color:
				try:
					curses.use_default_colors()
					self.has_default_colors=True
				except:
					self.has_default_colors=False
			self._setup_colour_pairs()
			curses.noecho()
			curses.meta(1)
			curses.halfdelay(10) # don't wait longer than 1s for keypress
			self.s.keypad(0)
			self.s.scrollok(1)
			return fn()
		finally:
			curses.echo()
			self._curs_set(1)
			try:
				curses.endwin()
			except:
				pass # don't block original error with curses error

	def _setup_colour_pairs(self):
	
		k = 1
		if self.has_color:
			if len(self.curses_pairs) > curses.COLOR_PAIRS:
				raise Exception("Too many colour pairs!  Use fewer combinations.")
		
			for fg,bg in self.curses_pairs[1:]:
				if not self.has_default_colors and fg == -1:
					fg = _curses_colours["black"][0]
				if not self.has_default_colors and bg == -1:
					bg = _curses_colours["light gray"][0]
				curses.init_pair(k,fg,bg)
				k+=1
		else:
			wh, bl = curses.COLOR_WHITE, curses.COLOR_BLACK
		
		self.attrconv = {}
		for name, (cp, a, mono) in self.palette.items():
			if self.has_color:
				self.attrconv[name] = curses.color_pair(cp)
				if a: self.attrconv[name] |= curses.A_BOLD
			elif type(mono)==type(()):
				attr = 0
				for m in mono:
					attr |= self._curses_attr(m)
				self.attrconv[name] = attr
			else:
				attr = self._curses_attr(mono)
				self.attrconv[name] = attr
	
	def _curses_attr(self, a):
		if a == 'bold':
			return curses.A_BOLD
		elif a == 'standout':
			return curses.A_STANDOUT
		elif a == 'underline':
			return curses.A_UNDERLINE
		else:
			return 0
				
				


	def _curs_set(self,x):
		if self.cursor_state== "fixed" or x == self.cursor_state: 
			return
		try:
			curses.curs_set(x)
			self.cursor_state = x
		except:
			self.cursor_state = "fixed"

	
	def _clear(self):
		self.s.clear()
		self.s.refresh()
	
	
	def _getch(self, wait_tenths):
		if wait_tenths==0:
			return self._getch_nodelay()
		curses.halfdelay(wait_tenths)
		self.s.nodelay(0)
		return self.s.getch()
	
	def _getch_nodelay(self):
		self.s.nodelay(1)
		while 1:
			# this call fails sometimes, but seems to work when I try again
			try:
				curses.cbreak()
				break
			except:
				pass
			
		return self.s.getch()

	def set_input_timeouts(self, max_wait=0.5, complete_wait=0.1, 
		resize_wait=0.1):
		"""
		Set the get_input timeout values.  All values have a granularity
		of 0.1s, ie. any value between 0.15 and 0.05 will be treated as
		0.1 and any value less than 0.05 will be treated as 0. 
	
		max_wait -- amount of time in seconds to wait for input when
			there is no input pending
		complete_wait -- amount of time in seconds to wait when
			get_input detects an incomplete escape sequence at the
			end of the available input
		resize_wait -- amount of time in seconds to wait for more input
			after receiving two screen resize requests in a row to
			stop urwid from consuming 100% cpu during a gradual
			window resize operation
		"""

		def convert_to_tenths( s ):
			return int( (s+0.05)*10 )

		self.max_tenths = convert_to_tenths(max_wait)
		self.complete_tenths = convert_to_tenths(complete_wait)
		self.resize_tenths = convert_to_tenths(resize_wait)
	
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
		
		When double-byte encoding is not enabled
		"Extended ASCII" characters:  "\\xa1", "\\xb2", "\\xfe"

		When double-byte encoding is enabled
		Double-byte characters:  "\\xa1\\xea", "\\xb2\\xd4"
		"""
		
		keys, raw = self._get_input( self.max_tenths )
		
		# Avoid pegging CPU at 100% when slowly resizing, and work
		# around a bug with some braindead curses implementations that 
		# return "no key" between "window resize" commands 
		if keys==['window resize'] and self.prev_input_resize:
			while True:
				keys, raw2 = self._get_input(self.resize_tenths)
				raw += raw2
				if not keys:
					keys, raw2 = self._get_input( 
						self.resize_tenths)
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
		
		
	def _get_input(self, wait_tenths):
		# this works around a strange curses bug with window resizing 
		# not being reported correctly with repeated calls to this
		# function without a doupdate call in between
		curses.doupdate() 
		
		key = self._getch(wait_tenths)
		resize = False
		raw = []
		keys = []
		
		while key >= 0:
			raw.append(key)
			if key==WINDOW_RESIZE: 
				resize = True
				key = self._getch_nodelay()
				continue
			keys.append(key)
			key = self._getch_nodelay()

		processed = []
		
		def more_fn(raw=raw,
				# hide warnings in python 2.1
				self_getch=self._getch, 
				self_complete_tenths = self.complete_tenths):
			key = self_getch(self_complete_tenths)
			if key >= 0:
				raw.append(key)
			return key
			
		while keys:
			run, keys = self._process_keyqueue(keys, more_fn)
			processed += run

		if resize:
			processed.append('window resize')

		return processed, raw
		
	def _process_keyqueue(self, keys, more_fn):
		code = keys.pop(0)
		if code >= 32 and code <= 126:
			key = chr(code)
			return [key],keys
		if _keyconv.has_key(code):
			return [_keyconv[code]],keys
		if code >0 and code <27:
			return ["ctrl %s" % chr(ord('a')+code-1)],keys
		if code < 256 and util.within_double_byte(chr(code),0,0):
			if not keys:
				key = more_fn()
				if key >= 0: keys.append(key)
			if keys and key[0] < 256:
				db = chr(code)+chr(keys[0])
				if util.within_double_byte( db, 0, 1 ):
					keys.pop(0)
					return [db],keys
		if code >127 and code <256:
			key = chr(code)
			return [key],keys
		if code != 27:
			return ["<%d>"%code],keys

		result = _escape_trie.get( keys, more_fn )
		
		if result is not None:
			result, keys = result
			return [result],keys

		if keys:
			# Meta keys -- ESC+Key form
			run, keys = self._process_keyqueue(keys, more_fn)
			if run[0] == "esc" or "meta " in run[0]:
				return ['esc']+run, keys
			return ['meta '+run[0]]+run[1:], keys
			
		return ['esc'],keys
		
			

	def _dbg_instr(self): # messy input string (intended for debugging)
		curses.echo()
		str = self.s.getstr()
		curses.noecho()
		return str
		
	def _dbg_out(self,str): # messy output function (intended for debugging)
		self.s.clrtoeol()
		self.s.addstr(str)
		self.s.refresh()
		self._curs_set(1)
		
	def _dbg_query(self,question): # messy query (intended for debugging)
		self.dbg_out(question)
		return self.dbg_instr()
	
	def _dbg_refresh(self):
		self.s.refresh()



	def get_cols_rows(self):
		"""Return the terminal dimensions (num columns, num rows)."""
		rows,cols = self.s.getmaxyx()
		return cols,rows
		

	def _setattr(self, a):
		if a is None:
			self.s.attrset( 0 )
			return
		if not self.attrconv.has_key(a):
			raise Exception, "Attribute %s not registered!"%`a`
		self.s.attrset( self.attrconv[a] )
				
			
			
	def draw_screen(self, (cols, rows), r ):
		"""Paint screen with rendered canvas."""
		lines = r.text
		
		assert len(lines) == rows, `len(lines),rows`
	
		for y in range(len(lines)):
			line = lines[y].translate( _trans_table )
			if len(line) < cols:
				line += " "*(cols-len(line))
			if y == rows-1:
				# don't draw in the lower right corner
				line = line[:cols-1]
				
			if len(r.attr) > y:
				attr = r.attr[y]
			else:
				attr = []
			col = 0
			
			try:
				self.s.move( y, 0 )
			except:
				# terminal shrunk? 
				# move failed so stop rendering.
				break
			
			for a, run in attr:
				self._setattr(a)
				self.s.addstr( line[col:col+run] )
				col += run

			if len(line) > col:
				self._setattr( None )
				self.s.addstr( line[col:] )
			
		if r.cursor is not None:
			x,y = r.cursor
			self._curs_set(1)
			try:
				self.s.move(y,x)
			except:
				pass
		else:
			self._curs_set(0)
			self.s.move(0,0)
		
		self.s.refresh()






class _test:
	def __init__(self):
		self.ui = Screen()
		self.l = _curses_colours.keys()
		self.l.sort()
		for c in self.l:
			self.ui.register_palette( [
				(c+" on black", c, 'black', 'underline'),
				(c+" on dark blue",c, 'dark blue', 'bold'),
				(c+" on light gray",c,'light gray', 'standout'),
				])
		self.ui.run_wrapper(self.run)
		
	def run(self):
		class FakeRender: pass
		r = FakeRender()
		text = ["  has_color = "+`self.ui.has_color`,""]
		attr = [[],[]]
		r.coords = {}
		r.cursor = None
		
		for c in self.l:
			t = ""
			a = []
			for p in c+" on black",c+" on dark blue",c+" on light gray":
				
				a.append((p,27))
				t=t+ (p+27*" ")[:27]
			text.append( t )
			attr.append( a )

		text += ["","return values from get_input(): (q exits)", ""]
		attr += [[],[],[]]
		cols,rows = self.ui.get_cols_rows()
		keys = None
		while keys!=['q']:
			r.text=([t.ljust(cols) for t in text]+[""]*rows)[:rows]
			r.attr=(attr+[[]]*rows) [:rows]
			self.ui.draw_screen((cols,rows),r)
			keys, raw = self.ui.get_input( raw_keys = True )
			if 'window resize' in keys:
				cols, rows = self.ui.get_cols_rows()
			if not keys:
				continue
			t = ""
			a = []
			for k in keys:
				t += "'"+k + "' "
				a += [(None,1), ('yellow on dark blue',len(k)),
					(None,2)]
			
			text.append(t + ": "+ `raw`)
			attr.append(a)
			text = text[-rows:]
			attr = attr[-rows:]
				
				


if '__main__'==__name__:
	_test()
