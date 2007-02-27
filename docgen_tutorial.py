#!/usr/bin/python
#
# Urwid tutorial documentation generation program
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

from __future__ import nested_scopes

import sys
import re

import urwid.html_fragment
import urwid
try:
	import templayer
except:
	templayer = None

examples = {}

interp_line = "#!/usr/bin/python\n\n"
cut_comment = "# CUT HERE"

examples["min"] = ["example_min"]
def example_min():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	def run():
		canvas = urwid.TextCanvas(None, ["Hello World"])
		ui.draw_screen( (20, 1), canvas )
		
		while not ui.get_input():
			pass
	
	ui.run_wrapper( run )

examples["text"] = ["example_text"]
def example_text():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	def run():
		cols, rows = ui.get_cols_rows()

		txt = urwid.Text("Hello World", align="center")
		fill = urwid.Filler( txt )

		canvas = fill.render( (cols, rows) )
		ui.draw_screen( (cols, rows), canvas )

		while not ui.get_input():
			pass

	ui.run_wrapper( run )

examples["attr"] = ["example_attr"]
def example_attr():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	ui.register_palette( [
		('banner', 'black', 'light gray', ('standout', 'underline')),
		('streak', 'black', 'dark red', 'standout'),
		('bg', 'black', 'dark blue'),
		] )

	def run():
		cols, rows = ui.get_cols_rows()

		txt = urwid.Text(('banner', " Hello World "), align="center")
		wrap1 = urwid.AttrWrap( txt, 'streak' )
		fill = urwid.Filler( wrap1 )
		wrap2 = urwid.AttrWrap( fill, 'bg' )

		canvas = wrap2.render( (cols, rows) )
		ui.draw_screen( (cols, rows), canvas )

		while not ui.get_input():
			pass

	ui.run_wrapper( run )

examples["resize"] = ["example_resize"]
def example_resize():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	ui.register_palette( [
		('banner', 'black', 'light gray', ('standout', 'underline')),
		('streak', 'black', 'dark red', 'standout'),
		('bg', 'black', 'dark blue'),
		] )

	def run():
		cols, rows = ui.get_cols_rows()

		txt = urwid.Text(('banner', " Hello World "), align="center")
		wrap1 = urwid.AttrWrap( txt, 'streak' )
		fill = urwid.Filler( wrap1 )
		wrap2 = urwid.AttrWrap( fill, 'bg' )

		while True:
			canvas = wrap2.render( (cols, rows) )
			ui.draw_screen( (cols, rows), canvas )

			keys = ui.get_input()
			if "q" in keys or "Q" in keys:
				break
			if "window resize" in keys:
				cols, rows = ui.get_cols_rows()	

	ui.run_wrapper( run )

examples["edit"] = ["example_edit"]
def example_edit():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	def run():
		cols, rows = ui.get_cols_rows()

		ask = urwid.Edit("What is your name?\n")
		fill = urwid.Filler( ask )
		reply = None

		while True:
			canvas = fill.render( (cols, rows), focus=True )
			ui.draw_screen( (cols, rows), canvas )

			keys = ui.get_input()
			for k in keys:
				if k == "window resize":
					cols, rows = ui.get_cols_rows()
					continue
				if reply is not None:
					return
				if k == "enter": 
					reply = urwid.Text( "Nice to meet you,\n"+
						ask.edit_text+"." )
					fill.body = reply
				if fill.selectable():
					fill.keypress( (cols, rows), k )

	ui.run_wrapper( run )

examples["frlb"] = ["example_frlb"]
def example_frlb():
	import urwid.curses_display
	import urwid

	class Conversation(object):
		def __init__(self):
			self.listbox = urwid.ListBox([self.new_question()])
			self.items = self.listbox.body
			instruct = urwid.Text("Press F8 to exit.")
			header = urwid.AttrWrap( instruct, 'header' )
			self.top = urwid.Frame(self.listbox, header)

		def main(self):
			self.ui = urwid.curses_display.Screen()
			self.ui.register_palette([
				('header', 'black', 'dark cyan', 'standout'),
				('I say', 'default', 'default', 'bold'),
				])
			self.ui.run_wrapper( self.run )
		# CUT HERE				
		def run(self):
			size = self.ui.get_cols_rows()

			while True:
				self.draw_screen( size )
				keys = self.ui.get_input()
				if "f8" in keys: 
					break
				for k in keys:
					if k == "window resize":
						size = self.ui.get_cols_rows()
						continue
					self.top.keypress( size, k )
				if keys:
					name = self.items[0].edit_text
					self.items[1:2] = [self.new_answer(name)]
		# CUT HERE
		def draw_screen(self, size):
			canvas = self.top.render( size, focus=True )
			self.ui.draw_screen( size, canvas )
		
		def new_question(self):
			return urwid.Edit(('I say',"What is your name?\n"))
		
		def new_answer(self, name):
			return urwid.Text(('I say',"Nice to meet you, "+name+"\n"))
			
	Conversation().main()

examples["lbcont"]=["example_lbcont"]
def example_lbcont():
	import urwid.curses_display
	import urwid

	class Conversation(object):
		def __init__(self):
			self.listbox = urwid.ListBox([self.new_question()])
			self.items = self.listbox.body
			instruct = urwid.Text("Press F8 to exit.")
			header = urwid.AttrWrap( instruct, 'header' )
			self.top = urwid.Frame(self.listbox, header)

		def main(self):
			self.ui = urwid.curses_display.Screen()
			self.ui.register_palette([
				('header', 'black', 'dark cyan', 'standout'),
				('I say', 'default', 'default', 'bold'),
				])
			self.ui.run_wrapper( self.run )
		# CUT HERE				
		def run(self):
			size = self.ui.get_cols_rows()

			while True:
				self.draw_screen( size )
				keys = self.ui.get_input()
				if "f8" in keys: 
					break
				for k in keys:
					if k == "window resize":
						size = self.ui.get_cols_rows()
						continue
					self.keypress( size, k )
						
		def keypress(self, size, k):
			if k == "enter":
				widget, pos = self.listbox.get_focus()
				if not hasattr(widget,'get_edit_text'):
					return
				
				answer = self.new_answer( widget.get_edit_text() )
				
				if pos == len(self.items)-1:
					self.items.append( answer )
					self.items.append( self.new_question() )
				else:
					self.items[pos+1:pos+2] = [answer]

				self.listbox.set_focus( pos+2, coming_from='above' )
				widget, pos = self.listbox.get_focus()
				widget.set_edit_pos(0)
			else:
				self.top.keypress( size, k )
		# CUT HERE
		def draw_screen(self, size):
			canvas = self.top.render( size, focus=True )
			self.ui.draw_screen( size, canvas )
		
		def new_question(self):
			return urwid.Edit(('I say',"What is your name?\n"))
		
		def new_answer(self, name):
			return urwid.Text(('I say',"Nice to meet you, "+name+"\n"))
			
	Conversation().main()

examples["lbscr"] = ["example_lbscr"]
def example_lbscr():
	import urwid.curses_display
	import urwid
	# CUT HERE
	CONTENT = [ urwid.AttrWrap( w, None, 'reveal focus' ) for w in [
		urwid.Text("This is a text string that is fairly long"),
		urwid.Divider("-"),
		urwid.Text("Short one"),
		urwid.Text("Another"),
		urwid.Divider("-"),
		urwid.Text("What could be after this?"),
		urwid.Text("The end."),
	] ]
	# CUT HERE
	class RevealFocus(object):
		def __init__(self):
			self.listbox = urwid.ListBox( CONTENT )
			self.head = urwid.Text("Pressed:")
			self.head = urwid.AttrWrap(self.head, 'header')
			self.top = urwid.Frame(self.listbox, self.head)

		def main(self):
			self.ui = urwid.curses_display.Screen()
			self.ui.register_palette([
				('header', 'white', 'black'),
				('reveal focus', 'black', 'dark cyan', 'standout'),
				])
			self.ui.run_wrapper( self.run )
		
		def run(self):
			size = self.ui.get_cols_rows()

			while True:
				self.draw_screen( size )
				keys = self.ui.get_input()
				if "f8" in keys: 
					break
				self.head.set_text("Pressed:")
				for k in keys:
					if k == "window resize":
						size = self.ui.get_cols_rows()
						continue
					self.head.set_text("Pressed: "+k)
					self.top.keypress( size, k )

		def draw_screen(self, size):
			canvas = self.top.render( size, focus=True )
			self.ui.draw_screen( size, canvas )
		
	RevealFocus().main()

examples["wmod"] = ["example_wmod"]
def example_wmod():
	class QuestionnaireItem( urwid.WidgetWrap ):
		def __init__(self):
			self.options = []
			unsure = urwid.RadioButton( self.options, "Unsure" )
			yes = urwid.RadioButton( self.options, "Yes" )
			no = urwid.RadioButton( self.options, "No" )
			display_widget = urwid.GridFlow( [unsure, yes, no],
				15, 3, 1, 'left' )
			urwid.WidgetWrap.__init__(self, display_widget)
		
		def get_state(self):
			for o in self.options:
				if o.get_state() is True:
					return o.get_label()

		
examples["wanat"] = ["example_wanat","example_wanat_new","example_wanat_multi"]
def example_wanat():
	class Pudding( urwid.FlowWidget ):
		def selectable( self ):
			return False
		def rows( self, (maxcol,), focus=False ):
			return 1
		def render( self, (maxcol,), focus=False ):
			num_pudding = maxcol / len("Pudding")
			return urwid.TextCanvas((self, (maxcol,), focus),
				["Pudding"*num_pudding]) 

	class BoxPudding( urwid.BoxWidget ):
		def selectable( self ):
			return False
		def render( self, (maxcol, maxrow), focus=False ):
			num_pudding = maxcol / len("Pudding")
			return urwid.TextCanvas((self, (maxcol, maxrow), focus),
				["Pudding"*num_pudding] * maxrow)

def example_wanat_new():
	class NewPudding( urwid.FlowWidget ):
		def selectable( self ):
			return False
		def rows( self, (maxcol,), focus=False ):
			w = self.display_widget( (maxcol,), focus )
			return w.rows( (maxcol,), focus )
		def render( self, (maxcol,), focus=False ):
			w = self.display_widget( (maxcol,), focus )
			return w.render( (maxcol,), focus )
		def display_widget( self, (maxcol,), focus ):
			num_pudding = maxcol / len("Pudding")
			return urwid.Text( "Pudding"*num_pudding )

def example_wanat_multi():
	class MultiPudding( urwid.Widget ):
		def selectable( self ):
			return False
		def rows( self, (maxcol,), focus=False ):
			return 1
		def render( self, size, focus=False ):
			if len(size) == 1:
				(maxcol,) = size
				maxrow = 1
			else:
				(maxcol, maxrow) = size
			num_pudding = maxcol / len("Pudding")
			return urwid.TextCanvas((self, size, focus),
				["Pudding"*num_pudding] * maxrow )

examples["wsel"] = ["example_wsel"]
def example_wsel():
	class SelectablePudding( urwid.FlowWidget ):
		def __init__( self ):
			self.pudding = "pudding"
		def selectable( self ):
			return True
		def rows( self, (maxcol,), focus=False ):
			return 1
		def render( self, (maxcol,), focus=False ):
			num_pudding = maxcol / len(self.pudding)
			pudding = self.pudding
			if focus: 
				pudding = pudding.upper()
			return urwid.TextCanvas((self, (maxcol,), focus),
				[pudding*num_pudding] )
		def keypress( self, (maxcol,), key ):
			if len(key)>1:
				return key
			if key.lower() in self.pudding:
				# remove letter from pudding
				n = self.pudding.index(key.lower())
				self.pudding = self.pudding[:n]+self.pudding[n+1:]
				if not self.pudding:
					self.pudding = "pudding"
			else:
				return key

examples["wcur"] = ["example_wcur"]
def example_wcur():
	class CursorPudding( urwid.FlowWidget ):
		def __init__( self ):
			self.cursor_col = 0
		def selectable( self ):
			return True
		def rows( self, (maxcol,), focus=False ):
			return 1
		def render( self, (maxcol,), focus=False ):
			num_pudding = maxcol / len("Pudding")
			cursor = None
			if focus:
				cursor = self.get_cursor_coords((maxcol,))
			return urwid.TextCanvas((self, (maxcol,), focus),
				["Pudding"*num_pudding], [], cursor )
		def get_cursor_coords( self, (maxcol,) ):
			col = min(self.cursor_col, maxcol-1)
			return col, 0
		def keypress( self, (maxcol,), key ):
			if key == 'left':
				col = self.cursor_col -1
			elif key == 'right':
				col = self.cursor_col +1
			else:
				return key
			self.cursor_x = max(0, min( maxcol-1, col ))
		# CUT HERE
		def get_pref_col( self, (maxcol,) ):
			return self.cursor_x
		def move_cursor_to_coords( self, (maxcol,), col, row ):
			assert row == 0
			self.cursor_x = col
			return True
			
def read_sections(tmpl):
	"""Read section tags, section descriptions, and column breaks from
	the Templayer template argument.  Convert the section data into a
	Python data structure called sections.  Each sublist of sections
	contains one column.  Each column contains a list of (tag, desc.)
	pairs.  Return sections."""

	sd = tmpl.layer("section_data")
	col_break = "---"
	sections = [[]]
	for ln in sd.split("\n"):
		if not ln: continue
		if ln == col_break:
			sections.append([])
			continue
		tag, desc = ln.split("\t",1)
		sections[-1].append( (tag, desc) )
	return sections

def read_example_code():
	"""By the time this function runs, the examples dictionary contains
	a list of function names, all starting with "example_".  Create a
	second dictionary called code_blocks.  Open the file containing this
	function.  For each function name in examples, read the text of that
	function into an entry in the code_blocks dictionary.  Return the
	code_blocks dictionary."""

	# invert the "examples" dictionary
	example_fns = {}
	for tag, l in examples.items():
		for i, fn in zip(range(len(l)), l):
			example_fns[fn] = tag, i
	
	# read our own source code
	# strip trailing spaces and tabs from each line
	code_blocks = {}
	current_block = None
	for ln in open( sys.argv[0], 'r').readlines():
		ln = ln.rstrip()
		if ( ln[:4] == "def " and ln[-3:] == "():" and
			example_fns.has_key( ln[4:-3] ) ):
			current_block = ln[4:-3]
			code_blocks[current_block] = []
			continue
		if ln and ln[:1] != "\t":
			current_block = None
			continue
		if current_block is None:
			continue
		if ln[:1] == "\t":
			ln = ln[1:]
		code_blocks[current_block].append(ln+"\n")
			
	# recombine code lines into a single string each
	for name, block in code_blocks.items():
		code_blocks[name] = "".join( block )
	
	return code_blocks

def filename(snum, inum, enum):
	"""Generate a filename to write an example to.  Take the section
	number from the table of contents, item number (subsection number),
	and example number.  Numbers start at 1.  Return the filename."""

	assert snum > 0, \
	 '%d.%d #%d: Section number should be greater than 0' % \
	 (snum, inum, enum)
	assert inum > 0, \
	 '%d.%d #%d: Item number should be greater than 0' % \
	 (snum, inum, enum)
	assert enum > 0, \
	 '%d.%d #%d: Example number should be greater than 0' % \
	 (snum, inum, enum)
	assert enum < 28, \
	 '%d.%d #%d: Example number should be less than 28' % \
	 (snum, inum, enum)

	if enum == 1:	estr = ''
	else:		estr = chr(ord('a') - 2 + enum)

	return "example" + str(snum) + "." + str(inum) + estr + ".py"

def write_example_files(sections, blocks):
	"""The sections dictionary gives section tags in the order used by
	the HTML output, and going through the tags in order allows us to
	generate the same section numbers that the HTML uses.  The global
	examples dictionary maps each section tag to a list of examples used
	in that section.  And the blocks dictionary maps each example tag
	to the text of that example.
	
	Generate section numbers and find the examples used in each section.
	Assume each example is ready to run -- replace the "cut here" comments
	with blank lines, but don't remove any code.  Create a file named
	according to the section number (and an optional letter to allow for
	multiple examples per section).  Write the cleaned-up example to the
	file."""

	cut_re = '^\s*' + re.escape(cut_comment) + '\s*$'
	cut_re_comp = re.compile(cut_re, re.MULTILINE)
	valid_re = 'import urwid' # some examples are not runnable
	valid_re_comp = re.compile(valid_re)
	snum = inum = enum = 0

	for col in sections:
		for tag, ignore in col:
			if not tag:
				# new section -- do its first item next time
				snum += 1
				inum = 0
				continue

			# new item inside a section
			inum += 1
			enum = 0
			for ename in examples.get(tag, []):
				etext = blocks[ename]
				if not valid_re_comp.search(etext):
					continue
				enum += 1
				fname = filename(snum, inum, enum)
				f = open(fname, 'w')
				etext = cut_re_comp.sub("", etext)
				etext = interp_line + etext.rstrip() + "\n"
				f.write(etext)
				f.close()

def cut_example_code(blocks):
	"""For brevity, the HTML gives excerpts from some of the examples.
	Convert the examples from the full forms stored in this file to the
	excerpted forms.  Use "cut here" comments in the examples, and the
	rules below, to do the conversion.  Also check that the full forms
	of certain examples contain identical code.  Also strip trailing
	spaces and tabs from the code.  Return a dictionary with the
	converted examples."""

	## do the conversions and the checks
	head1, ignore, tail1 = (
		blocks["example_frlb"].split(cut_comment+"\n") )
	blocks["example_frlb"] = (
		blocks["example_frlb"].replace(cut_comment,"") )
	
	head2, blocks["example_lbcont"], tail2 = (
		blocks["example_lbcont"].split(cut_comment+"\n") )
	assert head1 == head2, "frlb and lbcont have differing heads: "+\
		`head1, head2`
	assert tail1 == tail2, "frlb and lbcont have differing tails: "+\
		`tail1, tail2`

	ignore, blocks["example_lbscr"], ignore = (
		blocks["example_lbscr"].split(cut_comment+"\n") )

	blocks["example_wcur"], blocks["example_wcur2"] = (
		blocks["example_wcur"].split(cut_comment+"\n") )
	examples["wcur"].append("example_wcur2")
	
	# strip trailing spaces, tabs, blank lines from each block
	# removes spaces/tabs left by splitting at cut_comment
	for name, block in blocks.items():
		blocks[name] = block.rstrip()
	
	return blocks

def generate_example_results():
	"""Create HTML "screen shots" from the example programs defined in
	this file.  Store the results in a dictionary (mapping example tag
	to results) and return the dictionary."""

	results = {}
	
	init = urwid.html_fragment.screenshot_init
	collect = urwid.html_fragment.screenshot_collect

	init([],[[" "]])
	example_min()
	results["min"] = collect()[:1]

	init([(21,7)],[[" "]])
	example_text()
	results["text"] = collect()[:1]

	init([(21,7)],[[" "]])
	example_attr()
	results["attr"] = collect()[:1]

	init([(21,7),(10,9),(30,3),(15,2)],[["window resize"]]*3+[["q"]])
	example_resize()
	results["resize"] = collect()[:4]

	init([(21,7)],[list("Arthur, King of the Britons"),["enter"],[" "]])
	example_edit()
	results["edit"] = collect()[:3]

	init([(21,7)],[list("Tim t"),list("he Ench"),list("anter"),["f8"]])
	example_frlb()
	results["frlb"] = collect()[:4]

	init([(23,13)],[list("Abe")+["enter"]+list("Bob"),["enter"]+
		list("Carl")+["enter"], list("Dave")+["enter"], ["f8"]])
	example_lbcont()
	results["lbcont"] = collect()[1:4]

	init([(15,7), (20,9), (25,7), (11,13)],
	[["down"],["down"],["down"],["up"],["up"]] +
	[["window resize"]]*3 + [["f8"]])
	example_lbscr()
	results["lbscr"] = collect()[:9]

	return results

def generate_body(tmpl, sections, blocks, results):
	"""Assemble most of the HTML output (the body) from the pieces
	of text contained in all the arguments.  The body contains a table
	of contents followed by section headers and section text.  Pieces of
	section text may contain example code, and pieces of code may be
	followed by a "screen shot" of themselves.
	
	The sections dictionary gives the column formatting for the
	table of contents in the HTML and the description shared by the TOC
	entry and the section header.  With the addition of section numbers
	(generated now) sections contains the information needed to write
	the finished table of contents.  We expect the template to use
	two slots, toc_left and toc_right, which we fill with the TOC.
	We also expect the template to define two pieces of HTML,
	toc_section and toc_item, which give the formatting for all items
	in the TOC.

	While handling each entry in the TOC, we use the tag stored in
	sections to assemble the corresponding part of the body.  We expect
	the template to define two pieces of HTML, section_head and
	section_body, which give the formatting for all parts of the body
	(colored boxes for section headers, and the formatting that applies
	to all pieces of section text).  The template also defines one slot
	for each individual piece of section text, distinguished from the
	others by the section tag.
	
	Each individual body slot may use more slots to hold the examples
	and results included in a piece of section text.  These slots are
	numbered.  We use the section tags to look in the examples and
	results dictionaries; the dictionary order must match the numerical
	order used in the template.  We do not use example tags as defined
	in the global examples dictionary.  The blocks and results arguments
	describe which slots are defined; we hope the HTML text will use
	all the slots we have defined."""

	# put TOC columns into the variables used by the template
	# assign section numbers
	# generate HTML form of TOC entries, corresponding document parts
	assert len(sections) == 2, 'sections has %d columns but should have 2!' % len(sections)

	toc_slots = {'toc_left':[], 'toc_right':[]}
	body = []
	
	snum = inum = 0
	for slot, l in zip(['toc_left','toc_right'], sections):
		for tag, name in l:
			if not tag:
				# new section -- do its first item next time
				snum += 1
				inum = 0
				t = tmpl.format('toc_section', snum=`snum`,
					name=name )
				toc_slots[slot].append( t )
				b = tmpl.format('section_head', snum=`snum`,
					name=name )
				body.append( b )
				continue

			# new item inside a section
			inum += 1
			t = tmpl.format('toc_item', snum=`snum`, 
				inum=`inum`, name=name, tag=tag)
			toc_slots[slot].append( t )

			slots = {}
			i = 0
			for fn in examples.get(tag, []):
				slots['example[%d]'%i] = blocks[fn]
				i += 1
			i = 0
			for res in results.get(tag, []):
				slots['result[%d]'%i] = templayer.RawHTML(res)
				i += 1
			b = tmpl.format('body[%s]'%tag, ** slots )
			b = tmpl.format('section_body', snum=`snum`,
				inum=`inum`, name=name, tag=tag,
				content = b)
			body.append( b )
			
	return (body, toc_slots)

def parse_options():
	usage = "%s [-h|-?|--help]\n%s [-H|--HTML|--html] [-s|--scripts]" % \
	 (sys.argv[0], sys.argv[0])
	help = """%s options:

-h, -?, --help		Print this message to standard error and exit.

-H, --HTML, --html	Write the HTML documentation to standard output.
-s, --scripts		Write runnable scripts to files.""" % sys.argv[0]
	do_html = False
	do_scripts = False

	if len(sys.argv) < 2 or len(sys.argv) > 3:
		sys.exit(usage)

	if len(sys.argv) == 2 and (sys.argv[1] in ('-h', '-?', '--help')):
		sys.exit(help)

	for arg in sys.argv[1:]:
		if arg in ('-H', '--HTML', '--html'):
			if do_html:	sys.exit(usage)
			else:		do_html = True
		elif arg in ('-s', '--scripts'):
			if do_scripts:	sys.exit(usage)
			else:		do_scripts = True
		else:
			sys.exit(usage)

	return (do_html, do_scripts)

def main():
	(do_html, do_scripts) = parse_options()

	if templayer is None:
		sys.stderr.write(
"""Error importing templayer.  Please download and install the Templayer
python module available at:
http://excess.org/templayer/
""")
		sys.exit( 1 )

	tmpl = templayer.HtmlTemplate( "tmpl_tutorial.html" )
	sections = read_sections( tmpl )
	code_blocks = read_example_code()

	if do_scripts:
		write_example_files( sections, code_blocks )

	if do_html:
		code_blocks = cut_example_code( code_blocks )
		results = generate_example_results()
		out_file = tmpl.start_file()
		(body, toc_slots) = generate_body( tmpl, sections,
		                                   code_blocks, results )
		bottom = out_file.open( ** toc_slots )
		bottom.write( body )
		out_file.close()

if __name__=="__main__":
	main()
