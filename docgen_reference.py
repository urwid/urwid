#!/usr/bin/python
#
# Urwid reference documentation generation program
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

import pydoc
import urwid.curses_display
import urwid.raw_display
import urwid.web_display
import urwid.html_fragment
import urwid

import types

html_template = """<html>
<head>
<title>Urwid Reference</title>
<style type="text/css">
	h1 { text-align: center; }
	h2 { margin: 40px 0 0 0; padding: 10px;  background: #6d96e8;}
	h3 { margin: 0 0 3px 0; padding: 12px 6px 6px 6px; background: #efef96;}
	.l1 { margin: 12px 0 0 0; }
	.l2 { margin-left: 20px; }
</style>
<body>
<a name="top"></a>
<h1>Urwid Reference</h1>

<div style="text-align: center;">
<a href="http://excess.org/urwid/">Urwid Home Page</a> /
<a href="http://excess.org/urwid/examples.html">Example Screenshots</a> /
<a href="http://excess.org/urwid/utf8examples.html">UTF-8 Screenshots</a> /
<a href="tutorial.html">Tutorial</a> /
Reference
</div>
<br>
%s
</body>
</html>"""


class UrwidHTMLDoc( pydoc.HTMLDoc ):
	def heading(self, title, fgcol, bgcol, extras=''):
		return extras

	def section(self, title, fgcol, bgcol, contents, width=6,
	                prelude='', marginalia=None, gap='&nbsp;'):
		if " = " in title:
			visible, tail = title.split(" = ",1)
			aname = tail.split('">',1)[0]
			aname = aname.split('"',1)[1]
			aname = aname.replace(" ","_")
			title = '<a name="'+aname+'"></a>'+visible
		return '<h3>%s <span style="font-size:small; padding-left: 20px">[<a href="#top">back to top</a>]</span></h3>%s' % (title,contents)
		
	def namelink(self, name, *ignore):
		return name
	
	def classlink(self, obj, modname):
		return obj.__name__
	
	def modulelink(self, obj):
		return obj.__name__
	
	def modpkglink(self, (name, path, ispackage, shadowed) ):
		return name
	
	def markup(self, text, escape=None, funcs={}, classes={}, methods={}):
		return pydoc.HTMLDoc.markup( self, text, escape )

class WidgetInterface:
	def render(self, size, focus=False):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the canvas returned
		focus -- True if this widget is in focus
		
		Returns a canvas object.
		
		MUST be implemented.
		MUST NOT return a canvas with a cursor when focus=False.
		"""
	
	def rows(self, (maxcol,), focus=False):
		"""
		maxcol -- maximum screen columns for rendered widget
		focus -- True if this widget is in focus
		
		Returns an integer number or screen rows required.

		MUST be implemented by all flow widgets.
		MUST match the number of rows in the canvas returned by
		render function called with the same parameters.
		"""
	
	def selectable(self):
		"""
		Returns True if this widget will accept keyboard input and
		should take the focus when changing focus between widgets.

		MUST be implemented.
		"""
	
	def keypress(self, size, key):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the widget when rendered
		key -- key pressed
		
		Returns None if key was handled, returns key if not handled.

		MUST be implemented if selectable function returns True.
		MUST NOT be called if selectable function returns False.
		"""
	
	def get_cursor_coords(self, size):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the widget when rendered
			
		Returns (col,row) coordinates for cursor or None if no cursor.

		MUST be implemented if render function returns a canvas with
		a cursor.  
		MUST match the cursor in the canvas returned by render function
		when focus=True.
		Caller MUST treat no implementation as equivalent to an 
		implementation that always returns None.
		"""

	def get_pref_col(self, size):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the widget when rendered
			
		Returns the preferred screen column as an integer or None.

		Caller MUST treat no implementation as equivalent to an 
		implementation that always returns None.
		"""

	def move_cursor_to_coords(self, size, col, row):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the widget when rendered
		col -- desired screen column for cursor to appear, relative
		       to left edge of widget
		row -- desired screen row for cursor to appear, relative to
		       top edge of widget
			
		Returns True on success, False on failure.

		MUST succeed if there is any column on passed row that the
		cursor may be moved to.
		Caller MUST treat no implementation as equivalent to an
		implementation that always returns True.
		"""

	def mouse_event(self, size, event, button, col, row, focus):
		"""
		size -- flow widgets: (maxcol,)  box widgets: (maxcol,maxrow)
		        where maxcol and maxrow are the maximum screen columns
			and rows for the widget when rendered
		event -- event part of mouse event structure, eg. 'press',
		         'release', 'drag', 'meta press' etc..
		button -- button number for event between 1 and 5, may be 0
		          on button release events if button is unknown
		col -- screen column of event, relative to left edge of widget
		row -- screen row of event, relative to top edge of widget
		focus -- True if this widget is in focus
		
		Returns True if event was handled, False otherwise.

		Caller MUST treat no implementation as equivalent to an
		implementation that always returns False.
		"""

class ListWalkerInterface:
	def get_focus(self):
		"""
		Returns (widget, position).

		MUST be implemented.
		Caller MUST NOT assume that position object may be stored and
		reused after contents of list change.
		"""
	
	def set_focus(self, position):
		"""
		position -- a position returned by get_focus, get_next or
		            get_prev
		
		Returns None.
		
		MUST be implemented.
		"""
	
	def get_next(self, position):
		"""
		position -- a position returned by get_focus or get_next
		
		Returns (widget below, position below).

		MUST be implemented.
		Caller MUST NOT assume that position object may be stored and
		reused after contents of list change.
		"""
	
	def get_prev(self, position):
		"""
		position -- a position returned by get_focus or get_prev
		
		Returns (widget above, position above).

		MUST be implemented.
		Caller MUST NOT assume that position object may be stored and
		reused after contents of list change.
		"""



def main():
	html = UrwidHTMLDoc()
	contents = []
	doc = []
	contents.append('<table width="100%"><tr><td width="33%" valign="top">')
	
	for obj, name in [
		(None,"User interface wrappers"),
		(urwid.raw_display.Screen, "raw_display.Screen"),
		(urwid.curses_display.Screen, "curses_display.Screen"),
		(None,"Top-level widgets"),
		(urwid.BoxWidget, "BoxWidget"),
		(urwid.Frame, "Frame"),
		(urwid.Filler, "Filler"),
		(urwid.ListBox, "ListBox"),
		(urwid.SimpleListWalker, "SimpleListWalker"),
		(None,"Decorations"),
		(urwid.WidgetWrap, "WidgetWrap"),
		(urwid.AttrWrap, "AttrWrap"),
		(urwid.Padding, "Padding"),
		(urwid.Divider, "Divider"),
		(urwid.LineBox, "LineBox"),
		(urwid.SolidFill, "SolidFill"),
		(None,"Composite widgets"),
		(urwid.Columns, "Columns"),
		(urwid.Pile, "Pile"),
		(urwid.GridFlow, "GridFlow"),
		(urwid.BoxAdapter,"BoxAdapter"),
		(urwid.Overlay,"Overlay"),
		
		(None, None),

		(None,"Content widgets"),
		(urwid.FlowWidget, "FlowWidget"),
		(urwid.Text, "Text"),
		(urwid.Edit, "Edit"),
		(urwid.IntEdit, "IntEdit"),
		(urwid.Button, "Button"),
		(urwid.CheckBox, "CheckBox"),
		(urwid.RadioButton, "RadioButton"),
		(None, "Graphics"),
		(urwid.BarGraph, "BarGraph"),
		(urwid.GraphVScale, "GraphVScale"),
		(urwid.ProgressBar, "ProgressBar"),
		(None,"Urwid class interfaces"),
		(WidgetInterface, "Widget interface definition"),
		(ListWalkerInterface, "List Walker interface definition"),
		(None,"Canvas painting"),
		(urwid.Canvas, "Canvas"),
		(urwid.CanvasCombine, "CanvasCombine"),
		(urwid.CanvasJoin, "CanvasJoin"),
		
		(None, None),
		
		(None,"Custom formatting rules"),
		(urwid.TextLayout,"TextLayout"),
		(urwid.StandardTextLayout,"StandardTextLayout"),
		(None,"Character encoding"),
		(urwid.set_encoding,"set_encoding"),
		(urwid.get_encoding_mode,"get_encoding_mode"),
		(urwid.supports_unicode,"supports_unicode"),
		(None,"Screen capture"),
		(urwid.html_fragment.screenshot_init, "html_fragment.screenshot_init"),
		(urwid.html_fragment.screenshot_collect, "html_fragment.screenshot_collect"),
		(urwid.html_fragment.HtmlGenerator, "html_fragment.HtmlGenerator"),
		(None,"Web Application Interface"),
		(urwid.web_display.is_web_request,"web_display.is_web_request"),
		(urwid.web_display.set_preferences, "web_display.set_preferences"),
		(urwid.web_display.handle_short_request, "web_display.handle_short_request"),
		(urwid.web_display.Screen,"web_display.Screen"),
		]:
		if name is None:
			contents.append('</td><td width="33%" valign="top">')
		elif obj is None:
			contents.append('<div class="l1">%s</div>' % name)
			doc.append('<h2>%s</h2>' % name )
		else:
			lname = name
			if type(obj) != types.ClassType: #dirty hack
				doc.append('<a name="%s"></a><h3>function %s <span style="font-size:small; padding-left: 20px">[<a href="#top">back to top</a>]</span></h3>' % (name,name) )
			lname = lname.replace(" ","_")
			contents.append('<div class="l2">' +
				'<a href="#%s">%s</a></div>' % (lname,name) )
			doc.append( html.document( obj, name ) )
	
	contents.append("</td></tr></table>")
	
	print html_template % ( "".join(contents) + "".join(doc) )

if __name__ == "__main__":
	main()
