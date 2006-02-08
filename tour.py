#!/usr/bin/python
#
# Urwid tour.  It slices, it dices.. 
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
Urwid tour.  Shows many of the standard widget types and features.
"""

import urwid
import urwid.curses_display
import urwid.web_display

try: True # old python?
except: False, True = 0, 1

# use appropriate Screen class
if urwid.web_display.is_web_request():
	Screen = urwid.web_display.Screen
else:
	Screen = urwid.curses_display.Screen


blank = urwid.Text("")

HEADER = urwid.AttrWrap( urwid.Text("Welcome to the urwid tour!  "
	"UP / DOWN / PAGE UP / PAGE DOWN scroll.  F8 exits."), 'header')

B_PRESS_FRAME = None # this is set in TourDisplay.__init__
def B_PRESS( button ):
	B_PRESS_FRAME.footer = urwid.AttrWrap( urwid.Text(
		["Pressed: ",button.get_label()]), 'header')

RADIO_LIST = []

CONTENT = [
	blank,
	urwid.Padding( urwid.Text( [('important',"Text"),
		" widgets are the most common in "
		"any urwid program.  This Text widget was created without "
		"setting the wrap or align mode, so it defaults to left "
		"alignment with wrapping on space characters.  ",
		('important',"Change the window width"),
		" to see how the widgets on this page react.  "
		"This Text widget is wrapped with a ", ('important',"Padding"),
		" widget to keep it indented on the left and right."] ),
	('fixed left',2),('fixed right',2),20),	
	blank,
	urwid.Text( "This Text widget is right aligned.  Wrapped words stay "
	"to the right as well. ", align='right' ),
	blank,
	urwid.Text( "This one is center aligned.", align='center' ),
	blank,
	urwid.Text( "Text widgets may be clipped instead of wrapped.\n"
	"Extra text is discarded instead of wrapped to the next line. "
	"65-> 70-> 75-> 80-> 85-> 90-> 95-> 100>\n"
	"Newlines embedded in the string are still respected.", wrap='clip' ),
	blank,
	urwid.Text( "This is a right aligned and clipped Text widget.\n"
	"<100 <-95 <-90 <-85 <-80 <-75 <-70 <-65             "
	"Text will be cut off at the left of this widget.", align='right', 
	wrap='clip'),
	blank,
	urwid.Text( "Center aligned and clipped widgets will have text cut "
	"off both sides.", align='center', wrap='clip'),
	blank,
	urwid.Text( "The 'any' wrap mode will wrap on any character.  This "
	"mode will not collapse space characters at the end of the line but "
	"it still honors embedded newline characters.\nLike this one.", 
	wrap='any'),
	blank,
	urwid.Padding( urwid.Text("Padding widgets have many options.  This "
		"is a standard Text widget wrapped with a Padding widget "
		"with the alignment set to relative 20% and with its width "
		"fixed at 40."),
		('relative', 20), 40),
	blank,
	urwid.AttrWrap(urwid.Divider("=", 1), 'bright'),
	urwid.Padding( urwid.Text( ["The ",('important',"Divider"), 
		" widget repeats the same character across the whole line.  "
		"It can also add blank lines above and below."]),
	('fixed left',2),('fixed right',2),20),	
	urwid.AttrWrap(urwid.Divider("-", 0, 1), 'bright'),
	blank,
	urwid.Padding( urwid.Text( ["The ",('important',"Edit"), 
		" widget is a simple text editing widget.  It supports cursor "
		"movement and tries to maintain the current column when focus "
		"moves to another edit widget.  It wraps and aligns the same "
		"way as Text widgets." ] ),
	('fixed left',2),('fixed right',2),20),	
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This is a caption.  Edit here: "
	), "editable stuff" ), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This one supports newlines: "), 
	"line one starts them all\n"
	"== line 2 == with some more text to edit.. words.. whee..\n"
	"LINE III, the line to end lines one and two, unless you change "
	"something.", multiline=True ), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.Edit( ('editcp',"This one is clipped, try "
	"editing past the edge: "), "add some text here -> -> -> ....", 
	wrap='clip' ), 'editbx', 'editfc' ),
	blank,
	urwid.Text( "Different Alignments:" ),
	urwid.AttrWrap( urwid.Edit( "", "left aligned (default)", align='left' 
	), 'editbx', 'editfc' ),
	urwid.AttrWrap( urwid.Edit( "", "center aligned", align='center' 
	), 'editbx', 'editfc' ),
	urwid.AttrWrap( urwid.Edit( "", "right aligned", align='right' 
	), 'editbx', 'editfc' ),
	blank,
	urwid.AttrWrap( urwid.IntEdit( ('editcp',[('important',"IntEdit"),
	" allows only numbers: "]), 123 ), 'editbx', 'editfc' ),
	blank,
	urwid.Padding( urwid.AttrWrap( urwid.Edit( 
		('editcp',"Edit widget within a Padding widget "),""),
		'editbx','editfc' ),
	('fixed left',10),50 ),
	blank,
	blank,
	urwid.AttrWrap( urwid.Columns( [
		urwid.Divider("."),
		urwid.Divider(","),
		urwid.Divider("."),
		]), 'bright' ),
	blank,
	urwid.Columns( [
		urwid.Padding( urwid.Text( [('important',"Columns"), 
			" are used to share horizontal screen space.  "
			"This one splits the space into two parts with "
			"three characters between each column.  The "
			"contents of each column is a single widget."] ),
		('fixed left',2),('fixed right',0),20),
		urwid.Pile( [
			urwid.Divider("~"),
			urwid.Text( ["When you need to put more than one "
			"widget into a column you can use a ",('important',
			"Pile")," to combine two or more widgets."] ),
			urwid.Divider("_") ] )
		], 3 ),
	blank,
	blank,
	urwid.Columns( [
		urwid.Text( "Columns may be placed inside other columns."),
		urwid.Columns( [
			urwid.Text( "Col 2.1" ),
			urwid.Text( "Col 2.2" ),
			urwid.Text( "Col 2.3" ),
			], 1 ),
		], 2 ),
	blank,
	urwid.Padding( urwid.Text( "Columns may also have uneven relative "
		"weights or fixed widths.  Use a minimum width so that "
		"columns don't become too small."),
	('fixed left',2),('fixed right',2),20),	
	blank,
	urwid.Columns( [
		urwid.AttrWrap(urwid.Text("Weight 1"),'reverse'),
		('weight', 2, urwid.Text("Weight 2")),
		('weight', 3, urwid.AttrWrap(urwid.Text("Weight 3"),'reverse')),
		('weight', 4, urwid.Text("Weight 4")),
		('weight', 5, urwid.AttrWrap(urwid.Text("Weight 5"),'reverse')),
		('weight', 6, urwid.Text("Weight 6")),
		], 0, min_width=8 ),
	blank,
	urwid.Columns( [
		('weight', 2, urwid.AttrWrap(urwid.Text("Weight 2"),'reverse')),
		('fixed', 9, urwid.Text("<Fixed 9>")),
		('weight', 3, urwid.AttrWrap(urwid.Text("Weight 3"),'reverse')),
		('fixed', 14, urwid.Text("<--Fixed 14-->")),
		], 0, min_width=8 ),
	blank,
	urwid.Columns( [ urwid.AttrWrap( urwid.Edit( 
			('editcp',"Edit widget within Columns"),
			"here's\nsome\ninfo",
			multiline=True),
		'editbx','editfc'),
		urwid.Pile([ urwid.AttrWrap( urwid.Edit(
				('editcp',"and within Pile "),"more"),
				'editbx','editfc'),
				blank,
				urwid.AttrWrap( urwid.Edit(
				('editcp',"another "),"still more"),
				'editbx','editfc'),
			]),
		], 1 ),
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
	urwid.Padding(urwid.Text( ["A ",('important',"GridFlow")," widget "
		"may be used to display a list of flow widgets with equal "
		"widths.  Widgets that don't fit on the first line will "
		"flow to the next.  This is useful for small widgets that "
		"you want to keep together such as ",('important',"Button"),
		", ",('important',"CheckBox"), " and ",
		('important',"RadioButton"), " widgets." ]),
	('fixed left',2),('fixed right',2),20),	
	blank,
	urwid.Padding( urwid.GridFlow( [
		urwid.AttrWrap(urwid.Button("Yes",B_PRESS),'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("No",B_PRESS),'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("Perhaps",B_PRESS),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("Certainly",B_PRESS),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("Partially",B_PRESS),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("Tuesdays Only",B_PRESS),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.Button("Help",B_PRESS),
			'buttn','buttnf'),
		], 13,3,1, 'left'), 
		('fixed left',4),('fixed right',3)),
	blank,
	urwid.Padding( urwid.GridFlow( [
		urwid.AttrWrap(urwid.CheckBox("Wax"),'buttn','buttnf'),
		urwid.AttrWrap(urwid.CheckBox("Wash"),'buttn','buttnf'),
		urwid.AttrWrap(urwid.CheckBox("Buff"),'buttn','buttnf'),
		urwid.AttrWrap(urwid.CheckBox("Clear Coat"),'buttn','buttnf'),
		urwid.AttrWrap(urwid.CheckBox("Dry"),'buttn','buttnf'),
		urwid.AttrWrap(urwid.CheckBox("Racing Stripe"),
			'buttn','buttnf'),
		], 10,3,1, 'left') ,
		('fixed left',4),('fixed right',3)),
	blank,
	urwid.Padding( urwid.GridFlow( [
		urwid.AttrWrap(urwid.RadioButton(RADIO_LIST, "Morning"),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.RadioButton(RADIO_LIST, "Afternoon"),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.RadioButton(RADIO_LIST, "Evening"),
			'buttn','buttnf'),
		urwid.AttrWrap(urwid.RadioButton(RADIO_LIST, "Weekend"),
			'buttn','buttnf'),
		], 13,3,1, 'left') ,
		('fixed left',4),('fixed right',3)),
	blank,
	blank,
	urwid.Padding(urwid.Text( ["All these widgets have been diplayed "
		"with the help of a ", ('important',"ListBox"), " widget.  "
		"ListBox widgets handle scrolling and changing focus.  A ", 
		('important',"Frame"), " widget is used to keep the "
		"instructions at the top of the screen."]),
	('fixed left',2),('fixed right',2),20),	
	blank,
	blank,
	]
	
	



class TourDisplay:
	palette = [
		('body','black','light gray', 'standout'),
		('reverse','light gray','black'),
		('header','white','dark red', 'bold'),
		('important','dark blue','light gray',('standout','underline')),
		('editfc','white', 'dark blue', 'bold'),
		('editbx','light gray', 'dark blue'),
		('editcp','black','light gray', 'standout'),
		('bright','dark gray','light gray', ('bold','standout')),
		('buttn','black','dark cyan'),
		('buttnf','white','dark blue','bold'),
		]
	
	def __init__(self):
		self.listbox = urwid.ListBox( CONTENT )
		view = urwid.AttrWrap(self.listbox, 'body')
		self.view = urwid.Frame( view, header=HEADER )

		global B_PRESS_FRAME
		B_PRESS_FRAME = self.view
		
	
	def main(self):
		self.ui = Screen()
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
	urwid.web_display.set_preferences("Urwid Tour")
	# try to handle short web requests quickly
	if urwid.web_display.handle_short_request():
		return
		
	TourDisplay().main()
	
if '__main__'==__name__ or urwid.web_display.is_web_request():
	main()
