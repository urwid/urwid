#!/usr/bin/python
#
# Urwid main loop code
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

from util import *
from command_map import command_map

class ExitMainLoop(Exception):
	pass

def generic_main_loop(topmost_widget, palette=[], screen=None,
	handle_mouse=True, input_filter=None, unhandled_input=None):
	"""
	Initialize the palette and start a generic main loop handling
	input events and updating the screen.  The loop will continue
	until an ExitMainLoop exception is raised.  
	
	This function will call screen.run_wrapper() if screen.start() 
	has not already	been called.

	topmost_widget -- the widget used to draw the screen and handle input
	palette -- a palette to pass to the screen object's register_palette()
	screen -- a screen object, if None raw_display.Screen will be used.
	handle_mouse -- True: attempt to handle mouse events
	input_filter -- a function that is passed each input event and
		may return a new event or None to remove that event from
		further processing
	unhandled_input -- a function that is passed input events
		that neither input_filter nor the widgets have handled
	"""

	def run():
		if handle_mouse:
			screen.set_mouse_tracking()
		size = screen.get_cols_rows()
		while True:
			canvas = topmost_widget.render(size, focus=True)
			screen.draw_screen(size, canvas)
			keys = None
			while not keys:
				keys = screen.get_input()
			for k in keys:
				if input_filter:
					k = input_filter(k)
				if is_mouse_event(k):
					event, button, col, row = k
					if topmost_widget.mouse_event(size, 
						event, button, col, row, 
						focus=True ):
						k = None
				else:
					k = topmost_widget.keypress(size, k)
				if k and unhandled_input:
					k = unhandled_input(k)
				if k and command_map[k] == 'redraw screen':
					screen.clear()
			
			if 'window resize' in keys:
				size = screen.get_cols_rows()
	
	if not screen:
		import raw_display
		screen = raw_display.Screen()

	if palette:
		screen.register_palette(palette)
	try:
		if screen.started:
			run()
		else:
			screen.run_wrapper(run)
	except ExitMainLoop:
		pass


def iterable_main_loop(topmost_widget, palette=[], screen=None,
	handle_mouse=True, input_filter=None, unhandled_input=None):
	"""
	Initialize the palette and start an iterable main loop handling
	input events and updating the screen.  The loop will continue
	until an ExitMainLoop exception is raised.
	
	This function differs from generic_main_loop() in that it
	immediately returns an iterable object that must be iterated
	over to execute the loop.  The values returned are from the
	screen object's draw_screen method.  
	
	This function will call screen.run_wrapper() if screen.start() 
	has not already	been called.

	topmost_widget -- the widget used to draw the screen and handle input
	palette -- a palette to pass to the screen object's register_palette()
	screen -- a screen object, if None raw_display.Screen will be used.
	handle_mouse -- True: attempt to handle mouse events
	input_filter -- a function that is passed each input event and
		may return a new event or None to remove that event from
		further processing
	unhandled_input -- a function that is passed input events
		that neither input_filter nor the widgets have handled
	"""

	def run():
		if handle_mouse:
			screen.set_mouse_tracking()
		size = screen.get_cols_rows()
		try:
			while True:
				canvas = topmost_widget.render(size, focus=True)
				yield screen.draw_screen(size, canvas)
				keys = None
				while not keys:
					keys = screen.get_input()
				for k in keys:
					if input_filter:
						k = input_filter(k)
					if is_mouse_event(k):
						event, button, col, row = k
						if topmost_widget.mouse_event(size, 
							event, button, col, row, 
							focus=True ):
							k = None
					else:
						k = topmost_widget.keypress(size, k)
					if k and unhandled_input:
						k = unhandled_input(k)
					if k and command_map[k] == 'redraw screen':
						screen.clear()
				
				if 'window resize' in keys:
					size = screen.get_cols_rows()
		except ExitMainLoop:
			return
	
	if not screen:
		import raw_display
		screen = raw_display.Screen()

	if palette:
		screen.register_palette(palette)
	
	if screen.started:
		return run()
	else:
		return screen.run_wrapper(run)

