#!/usr/bin/python
#
# Urwid keyboard input test app
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
Keyboard test application
"""

import urwid.curses_display
import urwid.raw_display
import urwid.web_display
import urwid

import sys

try: True # old python?
except: False, True = 0, 1
		
if urwid.web_display.is_web_request():
	Screen = urwid.web_display.Screen
else:
	if len(sys.argv)>1 and sys.argv[1][:1] == "r":
		Screen = urwid.raw_display.Screen
	else:
		Screen = urwid.curses_display.Screen

class KeyTest:
	def __init__(self):
		self.ui = Screen()
		header = urwid.Text("Values from get_input(). Q exits.")
		header = urwid.AttrWrap(header,'header')
		self.l = []
		self.listbox = urwid.ListBox(self.l)
		listbox = urwid.AttrWrap(self.listbox, 'listbox')
		self.top = urwid.Frame( listbox, header )
		
	def main(self):
		self.ui.register_palette([
			('header', 'black', 'dark cyan', 'standout'),
			('key', 'yellow', 'dark blue', 'bold'),
			('listbox', 'light gray', 'black' ),
			])
		self.ui.run_wrapper(self.run)
	
	def run(self):
		self.ui.set_mouse_tracking()
		
		cols, rows = self.ui.get_cols_rows()

		keys = ['not q']
		while 'q' not in keys and 'Q' not in keys:
			if keys:
				self.ui.draw_screen((cols,rows),
					self.top.render((cols,rows),focus=True))
			keys, raw = self.ui.get_input(raw_keys=True)
			if 'window resize' in keys:
				cols, rows = self.ui.get_cols_rows()
			if not keys:
				continue
			t = []
			a = []
			for k in keys:
				if urwid.is_mouse_event(k):
					t += ["('",('key',k[0]),
						"', ", ('key',`k[1]`),
						", ", ('key',`k[2]`),
						", ", ('key',`k[3]`),
						") "]
				else:
					t += ["'",('key',k),"' "]
			
			rawt = urwid.Text(", ".join(["%d"%r for r in raw]))
			
			self.l.append(
				urwid.Columns([
					('weight',2,urwid.Text(t)),
					rawt])
				)
			self.listbox.set_focus(len(self.l)-1,'above')
				


def main():
	urwid.web_display.set_preferences('Input Test')
	if urwid.web_display.handle_short_request():
		return
	KeyTest().main()
	

if '__main__'==__name__ or urwid.web_display.is_web_request():
	main()
