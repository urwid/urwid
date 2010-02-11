#!/usr/bin/python
#
# Urwid reference documentation generation program
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

import pydoc
import urwid.curses_display
import urwid.raw_display
import urwid.web_display
import urwid.html_fragment
import urwid

import types

html_template = """<html>
<head>
<title>Urwid %version% Reference</title>
<style type="text/css">
    h1 { text-align: center; }
    h2 { margin: 40px 0 0 0; padding: 10px;  background: #6d96e8;}
    h3 { margin: 0 0 3px 0; padding: 12px 6px 6px 6px; background: #efef96;}
    .l1 { margin: 12px 0 0 0; }
    .l2 { margin-left: 20px; }
</style>
<body>
<a name="top"></a>
<h1>Urwid %version% Reference</h1>

<div style="text-align: center;">
<a href="http://excess.org/urwid/">Urwid Home Page</a> /
<a href="http://excess.org/urwid/examples.html">Example Screenshots</a> /
<a href="http://excess.org/urwid/utf8examples.html">UTF-8 Screenshots</a> /
<a href="tutorial.html">Tutorial</a> /
Reference
</div>
<br>
%toc%
<br>
[<b>F</b>] = Flow Widget displayed with assigned screen columns and variable screen rows<br>
[<b>B</b>] = Box Widget displayed with assigned screen columns and assigned screen rows<br>
[<b>F</b>/<b>B</b>] = May behave as either Flow Widget or Box Widget<br>
[<b>X</b>] = Fixed Widget has a fixed number of screen columns and rows
<br>
%contents%
</body>
</html>"""

flagd = {
    None: "",
    "B": "[<b>B</b>]",
    "F": "[<b>F</b>]",
    "FB": "[<b>F</b>/<b>B</b>]",
    "X": "[<b>X</b>]",
}


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
        
        MUST be implemented.  Should send "modified" signal (or call
        self._modified if inheriting from ListWalker)
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
    
    for obj, name, flag in [
        (None,"MainLoop & event loops", None),
        (urwid.MainLoop, "MainLoop", None),
        (urwid.SelectEventLoop, "SelectEventLoop", None),
        (urwid.GLibEventLoop, "GLibEventLoop", None),
        (urwid.TwistedEventLoop, "TwistedEventLoop", None),
        (None,"Top-level widgets",None),
        (urwid.Frame, "Frame", "B"),
        (urwid.Filler, "Filler", "B"),
        (urwid.ListBox, "ListBox", "B"),
        (None,"Decorations", None),
        (urwid.AttrMap, "AttrMap", "FB"),
        (urwid.Padding, "Padding", "FB"),
        (urwid.Divider, "Divider", "F"),
        (urwid.LineBox, "LineBox", "FB"),
        (urwid.SolidFill, "SolidFill", "B"),
        (None,"Composite widgets", None),
        (urwid.Columns, "Columns", "FB"),
        (urwid.Pile, "Pile", "FB"),
        (urwid.GridFlow, "GridFlow", "F"),
        (urwid.BoxAdapter,"BoxAdapter", "F"),
        (urwid.Overlay,"Overlay", "B"),
        (None,"Content widgets", None),
        (urwid.Text, "Text", "F"),
        (urwid.Edit, "Edit", "F"),
        (urwid.IntEdit, "IntEdit", "F"),
        (urwid.Button, "Button", "F"),
        (urwid.CheckBox, "CheckBox", "F"),
        (urwid.RadioButton, "RadioButton", "F"),
        
        (None, None, None),

        (None, "Graphics",None),
        (urwid.BarGraph, "BarGraph","B"),
        (urwid.GraphVScale, "GraphVScale","B"),
        (urwid.ProgressBar, "ProgressBar","F"),
        (urwid.BigText, "BigText","X"),
        (urwid.get_all_fonts, "get_all_fonts",None),
        (None,"Build custom widgets",None),
        (urwid.WidgetWrap, "WidgetWrap",None),
        (None,"Abstract widgets & interfaces",None),
        (WidgetInterface, "Widget interface definition",None),
        (urwid.Widget, "Widget",None),
        (urwid.BoxWidget, "BoxWidget",None),
        (urwid.FlowWidget, "FlowWidget",None),
        (urwid.FixedWidget, "FixedWidget",None),
        (urwid.WidgetDecoration, "WidgetDecoration", None),
        (ListWalkerInterface, "List Walker interface definition",None),
        (urwid.ListWalker, "ListWalker", None),
        (None,"ListBox list walkers",None),
        (urwid.PollingListWalker, "PollingListWalker",None),
        (urwid.SimpleListWalker, "SimpleListWalker",None),
        (None,"Canvas painting", None),
        (urwid.Canvas, "Canvas", None),
        (urwid.TextCanvas, "TextCanvas", None),
        (urwid.CompositeCanvas, "CompositeCanvas", None),
        (urwid.SolidCanvas, "SolidCanvas", None),
        (urwid.CanvasCombine, "CanvasCombine", None),
        (urwid.CanvasJoin, "CanvasJoin", None),
        (urwid.CanvasOverlay, "CanvasOverlay", None),
        (None, None, None),
        
        (None,"Raw screen attributes", None),
        (urwid.AttrSpec, "AttrSpec", None),
        (None,"Custom formatting rules", None),
        (urwid.TextLayout,"TextLayout", None),
        (urwid.StandardTextLayout,"StandardTextLayout", None),
        (None,"Character encoding", None),
        (urwid.set_encoding,"set_encoding", None),
        (urwid.get_encoding_mode,"get_encoding_mode", None),
        (urwid.supports_unicode,"supports_unicode", None),
        (None,"Signals", None),
        (urwid.connect_signal,"connect_signal", None),
        (urwid.disconnect_signal,"disconnect_signal", None),
        (urwid.register_signal,"register_signal", None),
        (urwid.emit_signal,"emit_signal", None),
        (None,"User interface wrappers",None),
        (urwid.raw_display.Screen, "raw_display.Screen",None),
        (urwid.curses_display.Screen, "curses_display.Screen",None),
        (urwid.web_display.Screen,"web_display.Screen",None),
        (None,"Screen capture", None),
        (urwid.html_fragment.screenshot_init, 
            "html_fragment.screenshot_init", None),
        (urwid.html_fragment.screenshot_collect, 
            "html_fragment.screenshot_collect", None),
        (urwid.html_fragment.HtmlGenerator, 
            "html_fragment.HtmlGenerator", None),
        (None,"Web Application Interface", None),
        (urwid.web_display.is_web_request,
            "web_display.is_web_request", None),
        (urwid.web_display.set_preferences, 
            "web_display.set_preferences", None),
        (urwid.web_display.handle_short_request, 
            "web_display.handle_short_request", None),
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
            thtm = flagd[flag]
            lname = lname.replace(" ","_")
            contents.append('<div class="l2">' +
                '<a href="#%s">%s</a> %s</div>' % 
                (lname,name,thtm) )
            doc.append( html.document( obj, name ) )
    
    contents.append("</td></tr></table>")
    
    h = html_template
    h = h.replace("%toc%", "".join(contents))
    h = h.replace("%contents%", "".join(doc))
    h = h.replace("%version%", urwid.__version__)
    print h

if __name__ == "__main__":
    main()
