#!/usr/bin/python
#
# Urwid tour.  It slices, it dices.. 
#    Copyright (C) 2004  Ian Ward
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

"""
Urwid tour.  Shows many of the standard widget types and features.
"""

import urwid
import urwid.curses_display

try: True # old python?
except: False, True = 0, 1
		

blank = urwid.Text("")

CONTENT = [
	urwid.AttrWrap( urwid.Text("Welcome to the urwid tour!  UP / DOWN / PAGE UP / PAGE DOWN scroll.  F8 exits."), 'header'),
	blank,
	blank,
	urwid.Text( [('important',"Text")," widgets are the most common in any urwid program.  This Text widget was created without setting the wrap or align mode, so it defaults to left alignment with wrapping on space characters.  ",('important',"Change the window width")," to see how the widgets on this page react."] ),
	blank,
	urwid.Text( "This Text widget is right aligned.  Wrapped words stay to the right as well. ", align='right' ),
	blank,
	urwid.Text( "This one is center aligned.", align='center' ),
	blank,
	urwid.Text( "Text widgets may be clipped instead of wrapped.\nExtra text is discarded instead of wrapped to the next line. 65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\nNewlines embedded in the string are still respected.", wrap='clip' ),
	blank,
	urwid.Text( "This is a right aligned and clipped Text widget.\n<100 <-95 <-90 <-85 <-80 <-75 <-70 <-65             Text will be cut off at the left of this widget.", align='right', wrap='clip'),
	blank,
	urwid.Text( "Center aligned and clipped widgets will have text cut off both sides.", align='center', wrap='clip'),
	blank,
	urwid.Text( "The 'any' wrap mode will wrap on any character.  This mode will not collapse space characters at the end of the line but it still honors embedded newline characters.\nLike this one.", wrap='any'),
	blank,
	urwid.AttrWrap(urwid.Divider("=", 1), 'bright'),
	urwid.Text( ["The ",('important',"Divider"), " widget repeats the same character across the whole line.  It can also add blank lines above and below."]),
	urwid.AttrWrap(urwid.Divider("-", 0, 1), 'bright'),
	blank,
	urwid.Text( ["The ",('important',"Edit"), " widget is a simple text editing widget.  It supports simple cursor movement and tries to maintain the current column when focus moves to another edit widget.  It wraps and aligns the same way as Text widgets." ] ),
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This is a caption.  Edit here: "), "editable stuff" ), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This one supports newlines: "), "line one starts them all\n== line 2 == with some more text to edit.. words.. whee..\nLINE III, the line to end lines one and two, unless you change something.", multiline=True ), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This one is clipped, try editing past the edge: "), "add some text here -> -> -> ....", wrap='clip' ), 'editbx', 'editfc' ),
	blank,
	urwid.Text( "Different Alignments:" ),
	urwid.AttrWrap( urwid.Edit( "", "left aligned (default)", align='left' ), 'editbx', 'editfc' ),
	urwid.AttrWrap( urwid.Edit( "", "center aligned", align='center' ), 'editbx', 'editfc' ),
	urwid.AttrWrap( urwid.Edit( "", "right aligned", align='right' ), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.IntEdit( ('editcp',[('important',"IntEdit")," allows only numbers: "]), 123 ), 'editbx', 'editfc' ),
	blank,
	blank,
	urwid.AttrWrap( urwid.Columns( [
		urwid.Divider("."),
		urwid.Divider(","),
		urwid.Divider("."),
		]), 'bright' ),
	blank,
	urwid.Columns( [
		urwid.Text( [('important',"Columns"), " are used to share horizontal screen space.  This one splits the space into two parts with three characters between each column.  The contents of each column is a single widget."] ),
		urwid.Pile( [
			urwid.Divider("~"),
			urwid.Text( ["When you need to put more than one widget into a column you can use a ",('important',"Pile")," to combine two or more widgets."] ),
			urwid.Divider("_") ] )
		], 3 ),
	blank,
	blank,
	urwid.Columns( [
		urwid.Text( "Columns may also be placed inside other columns."),
		urwid.Columns( [
			urwid.Text( "Col 2.1" ),
			urwid.Text( "Col 2.2" ),
			urwid.Text( "Col 2.3" ),
			], 1 ),
		], 2 ),
	blank,
	urwid.AttrWrap( urwid.Columns( [
		urwid.Divider("'"),
		urwid.Divider('"'),
		urwid.Divider("~"),
		urwid.Divider('"'),
		urwid.Divider("'"),
		]), 'bright' ),
	blank,
	blank,
	urwid.Text( ["All these widgets have been diplayed with the help of a ", ('important',"ListBox"), " widget.  ListBox widgets handle scrolling and changing focus.  ", ('important',"Frame"), " widgets may be used to place widgets above and/or below a listbox, as shown in the other example programs."]),
	blank,
	blank,
	]
	
	



class TourDisplay:
	palette = [
		('body','black','light gray', 'standout'),
		('header','white','dark red', 'bold'),
		('important','dark blue','light gray',('standout','underline')),
		('editfc','white', 'dark blue', 'bold'),
		('editbx','light gray', 'dark blue'),
		('editcp','black','light gray', 'standout'),
		('bright','dark gray','light gray', ('bold','standout')),
		]
	
	def __init__(self):
		self.listbox = urwid.ListBox( CONTENT )
		self.view = urwid.AttrWrap(self.listbox, 'body')
	
	def main(self):
		self.ui = urwid.curses_display.Screen()
		self.ui.register_palette( self.palette )
		self.ui.run_wrapper( self.run )
	
	def run(self):
		size = self.ui.get_cols_rows()
		while 1:
			canvas = self.view.render( size, focus=1 )
			self.ui.draw_screen( size, canvas )
			keys = None
			while not keys: 
				keys = self.ui.get_input()
			for k in keys:
				if k == 'window resize':
					size = self.ui.get_cols_rows()
				elif k == 'f8':
					return
				self.view.keypress( size, k )

def main():
	TourDisplay().main()
	
if __name__=="__main__": 
	main()
