#!/usr/bin/python
#
# Urwid tutorial documentation generation program
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

import sys

import urwid.html_fragment
import urwid

examples = {}
results = {}

examples["min"] = ["example_min"]
def example_min():
	import urwid.curses_display
	import urwid

	ui = urwid.curses_display.Screen()

	def run():
		canvas = urwid.Canvas( ["Hello World"] )
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

	class Conversation:
		def __init__(self):
			self.items = [ self.new_question() ]
			self.listbox = urwid.ListBox( self.items )
			instruct = urwid.Text("Press F1 to exit.")
			header = urwid.AttrWrap( instruct, 'header' )
			self.top = urwid.Frame(self.listbox, header)

		def main(self):
			self.ui = urwid.curses_display.Screen()
			self.ui.register_palette([
				('header', 'black', 'dark cyan', 'standout'),
				('I say', 'dark blue', 'default', 'bold'),
				])
			self.ui.run_wrapper( self.run )
		# CUT HERE				
		def run(self):
			size = self.ui.get_cols_rows()

			while True:
				self.draw_screen( size )
				keys = self.ui.get_input()
				if "f1" in keys: 
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

	class Conversation:
		def __init__(self):
			self.items = [ self.new_question() ]
			self.listbox = urwid.ListBox( self.items )
			instruct = urwid.Text("Press F1 to exit.")
			header = urwid.AttrWrap( instruct, 'header' )
			self.top = urwid.Frame(self.listbox, header)

		def main(self):
			self.ui = urwid.curses_display.Screen()
			self.ui.register_palette([
				('header', 'black', 'dark cyan', 'standout'),
				('I say', 'dark blue', 'default', 'bold'),
				])
			self.ui.run_wrapper( self.run )
		# CUT HERE				
		def run(self):
			size = self.ui.get_cols_rows()

			while True:
				self.draw_screen( size )
				keys = self.ui.get_input()
				if "f1" in keys: 
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
	class RevealFocus:
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
				if "f1" in keys: 
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
			return urwid.Canvas( ["Pudding"*num_pudding] )

	class BoxPudding( urwid.BoxWidget ):
		def selectable( self ):
			return False
		def render( self, (maxcol, maxrow), focus=False ):
			num_pudding = maxcol / len("Pudding")
			return urwid.Canvas( ["Pudding"*num_pudding] * maxrow )

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
	class MultiPudding:
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
			return urwid.Canvas( ["Pudding"*num_pudding] * maxrow )

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
			return urwid.Canvas( [pudding*num_pudding] )
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
			return urwid.Canvas( ["Pudding"*num_pudding], [], cursor )
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
			

def read_example_code():
	# reverse the "examples" dictionary
	fn_names = {}
	for tag, l in examples.items():
		for i, fn in zip(range(len(l)), l):
			fn_names[fn] = tag, i
	
	# read our own source code
	code_blocks = {}
	current_block = None
	for ln in open( sys.argv[0], 'r').readlines():
		ln = ln.rstrip()
		if ( ln[:4] == "def " and ln[-3:] == "():" and
			fn_names.has_key( ln[4:-3] ) ):
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
	
	# special handling for specific blocks
	head1, ignore, tail1 = (
		code_blocks["example_frlb"].split("# CUT HERE\n") )
	code_blocks["example_frlb"] = (
		code_blocks["example_frlb"].replace("# CUT HERE","") )
	
	head2, code_blocks["example_lbcont"], tail2 = (
		code_blocks["example_lbcont"].split("# CUT HERE\n") )
	assert head1 == head2, "frlb and lbcont have differing heads!"+`head1,head2`
	assert tail1 == tail2, "frlb and lbcont have differing tails!"

	ignore, code_blocks["example_lbscr"], ignore = (
		code_blocks["example_lbscr"].split("# CUT HERE\n") )

	code_blocks["example_wcur"], code_blocks["example_wcur2"] = (
		code_blocks["example_wcur"].split("# CUT HERE\n") )
	examples["wcur"].append("example_wcur2")
	
	
	# trim blank lines from end of each block
	for name, block in code_blocks.items():
		while block:
			i = block.rfind('\n',0,-1)
			if i == -1: break
			if block[i+1:-1].lstrip() == "":
				block = block[:i+1]
			else:
				break
		code_blocks[name] = block
		
	return code_blocks


def generate_example_results():
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

	init([(21,7)],[list("Tim t"),list("he Ench"),list("anter"),["f1"]])
	example_frlb()
	results["frlb"] = collect()[:4]

	init([(23,13)],[list("Abe")+["enter"]+list("Bob"),["enter"]+
		list("Carl")+["enter"], list("Dave")+["enter"], ["f1"]])
	example_lbcont()
	results["lbcont"] = collect()[1:4]

	init([(15,7), (20,9), (25,7), (11,13)],
	[["down"],["down"],["down"],["up"],["up"]] +
	[["window resize"]]*3 + [["f1"]])
	example_lbscr()
	results["lbscr"] = collect()[:9]

	return results

def main():
	try:
		import templayer
	except ImportError, e:
		sys.stderr.write(
"""Error importing templayer.  Please download and install the Templayer
python module available at:
http://excess.org/templayer/
""")
		sys.exit(1)
	
	tmpl = templayer.HtmlTemplate("tmpl_tutorial.html")
	out_file = tmpl.start_file()

	sd = tmpl.layer("section_data")
	toc = [[]]
	for ln in sd.split("\n"):
		if not ln: continue
		if ln == "---":
			toc.append([])
			continue
		tag, name = ln.split("\t",1)
		toc[-1].append( (tag, name) )

	code_blocks = read_example_code()
	results = generate_example_results()
	
	toc_slots = {'toc_left':[], 'toc_right':[]}
	body = []
	
	snum = inum = 0
	for toc_part, l in zip(['toc_left','toc_right'], toc):
		for tag, name in l:
			if not tag:
				snum += 1
				inum = 0
				t = tmpl.format('toc_section', snum=`snum`,
					name=name )
				toc_slots[toc_part].append( t )
				b = tmpl.format('section_head', snum=`snum`,
					name=name )
				body.append( b )
				continue
			inum += 1
			t = tmpl.format('toc_item', snum=`snum`, 
				inum=`inum`, name=name, tag=tag)
			toc_slots[toc_part].append( t )

			slots = {}
			i = 0
			for fn in examples.get(tag, []):
				slots['example[%d]'%i] = code_blocks[fn]
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
			
	bottom = out_file.open( ** toc_slots )
	bottom.write( body )
	out_file.close()

if __name__=="__main__":
	main()
