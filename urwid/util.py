#!/usr/bin/python
#
# Urwid utility functions
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

STANDARD_WRAP_MODES = ('any', 'space', 'clip')
STANDARD_ALIGN_MODES = ('left', 'center', 'right')

_custom_wrap_modes = {}
_custom_align_modes = {}

def valid_wrap_mode( x ):
	return x in STANDARD_WRAP_MODES or _custom_wrap_modes.has_key(x)

def valid_align_mode( x ):
	return x in STANDARD_ALIGN_MODES or _custom_align_modes.has_key(x)

def register_wrap_mode( x, fn ):
	"""Register custom wrap mode x function fn.

	Custom wrapping function:
	fn( text, width, wrap_mode )
		text -- original text string to wrap
		width -- max number of characters per row
		wrap_mode -- current wrap_mode
	Must return:
	list of offsets into text for line breaks

	eg. [4,6] would split "hallabaloo" into "hall","ab","aloo"
	"""
	_custom_wrap_modes[x] = fn

def register_align_mode( x, fn ):
	"""
	Register custom align mode x function fn.
	
	Custom alignment function:
	fn( text, width, b, wrap_mode, align_mode )
		text -- original text string to align
		b -- line breaks calculated from wrap_mode function
		wrap_mode -- current wrap_mode
		align_mode -- current align_mode
	Must return:
	line translation (see Text.get_line_translation for description)
	"""
	_custom_align_modes[x] = fn
	

def calculate_pos( trans, pref_col, row ):
	"""
	calculate_pos( translation, pref_col, row ) 
	-> new_pos
	"""

	if row < 0 or row >= len(trans):
		raise Exception("calculate_pos: out of translation row range")
	
	spos = 0
	if row > 0: spos = trans[row-1][-1]
	l_pad, l_trim, r_trim, epos = trans[row]

	pos = pref_col - l_pad + l_trim
	if pos < 0: pos = 0 # clamp to left edge

	pos = pos + spos
	if pos >= epos: 
		if row == len(trans)-1: # last row allow 1 extra
			pos = epos
		else:
			pos = epos-1 # clamp to right edge

	return pos 


	
def calculate_line_translation( text, width, wrap_mode, align_mode ):
	"""
	calculate_line_translation(..) -> [(l_pad, l_trim, r_trim, epos), ... ]
	
	one tuple per output line

	l_pad is the number of spaces that must be added to the line
	to follow the align_mode setting.
	
	l_trim and r_trim are the number of characters to be removed
	from the left and right sides of the line before display.
	
	epos is end position of this line in text.
	"""
	
	if _custom_wrap_modes.has_key( wrap_mode ):
		b = _custom_wrap_modes[ wrap_mode ]( text, width, wrap_mode )
	else:
		b = calculate_text_breaks( text, width, wrap_mode )

	if _custom_align_modes.has_key( align_mode ):
		return _custom_align_modes[ align_mode ]( text, width, b, wrap_mode, align_mode )
	else:
		return calculate_alignment( text, width, b, wrap_mode, align_mode )

def calculate_alignment( text, width, b, wrap_mode, align_mode ):

	last = 0
	l = []
	for p in b + [len(text)]:
		l_trim = r_trim = l_pad = 0
		line = text[last:p]
		
		if line[-1:] == "\n": r_trim = 1
		if wrap_mode == 'space':
			if line[-1:] == " ": r_trim = 1
		if wrap_mode == 'clip' and len(line) - l_trim - r_trim > width:
			# clip line to fit
			clip = len(line) - l_trim - r_trim - width
			if align_mode == 'right':
				l_trim += clip
			elif align_mode == 'center':
				ladd = clip / 2
				l_trim += ladd
				r_trim += clip - ladd
			else:
				r_trim += clip
		
		if align_mode in ('right', 'center'):
			ln = len(line) - r_trim - l_trim
			l_pad = width - ln
		if align_mode == 'center':
			l_pad = l_pad / 2
					
		l.append( (l_pad, l_trim, r_trim, p) )
		last = p
	return l
	

def calculate_text_breaks( text, width, mode ):
	"""
	calculate_text_breaks( text, width, mode ) -> mid_breaks
	
	mid_breaks is a list of offsets within text where the end of each
	line from 2..last will start.  ie. len(mid_breaks) = num lines-1
	"""
	b = []
	p = 0
	if mode == 'clip':
		# no wrapping to calculate, so it's easy.
		while 1:
			n_cr = text.find("\n", p)
			if n_cr == -1: return b
			p = n_cr +1
			b.append(p)
	while 1:
		# look for next eligable line break
		nb = _next_char_break(text, width, p)
		if not nb and p+width >= len(text):
			# no more cr's, last line fits
			break
		if not nb and mode == 'space':
			nb = _next_word_break(text, width, p)
		if not nb:
			nb = p+width
			if nb >= len(text): break
		p = nb
		b.append(p)
	return b


def _next_char_break( text, width, prev_break ):
	# only interested in newline characters
	cr_pos = text.find("\n", prev_break, prev_break+width+1)
	if cr_pos == -1:
		return
	return cr_pos+1

def _next_word_break( text, width, prev_break ):
	# find prev space
	sp_pos = text.rfind(" ", prev_break+1, prev_break+width+1)
	if sp_pos == -1: 
		return
	# wrap on last char in line? perfect.
	if sp_pos == prev_break + width:
		return sp_pos +1
	# wrapping word at end of string smaller than width, ok too.
	if sp_pos+1+width >= len(text):
		return sp_pos +1
	# don't wrap if word wrapped won't fit
	nsp_pos = text.find(" ",sp_pos+1,sp_pos+1+width)
	ncr_pos = text.find("\n",sp_pos+1,sp_pos+1+width)
	if ncr_pos == -1 and nsp_pos == -1:
		return
	return sp_pos +1


def positions_to_coords(plist, trans, clamp=1):
	"""
	positions_to_coords( position list, line translation [,clamp]) -> [(x,y), ... ]

	position list must be in ascending order, otherwise use
	position_to_coords on each position instead.

	if clamp is set (the default) then x coord will be clamped to the
	left clip edge and right clip edge+1, otherwise the x value may 
	be outside the translation or clipping area.
	"""
	y = 0
	beforelast = 0,0
	last = 0
	l = []
	plist_pos = 0
	for (l_pad, l_trim, r_trim, epos) in trans: 
		while plist[plist_pos] < epos:
			x = plist[plist_pos] - last
			if clamp:
				# outside trimming margins?  clamp to edge.
				if x < l_trim:
					x = l_trim
				if x > epos-last-r_trim:
					x = epos-last-r_trim
			# shift from padding and l_trim
			x += l_pad - l_trim
			
			l.append( (x,y) )

			plist_pos += 1
			if len(plist) == plist_pos:
				return l
		beforelast = last, y
		last = epos
		y += 1
	# clamp to end
	x,y = beforelast
	x = last - x + l_pad - l_trim
	for p in plist[plist_pos:]:
		l.append( (x, y) )
	return l

def position_to_coords( pos, trans, clamp=1 ):
	"""
	position_to_coords( position, line translation [,clamp]) -> (x,y)
	"""
	[(x,y)] = positions_to_coords( [pos], trans, clamp )
	return (x,y)


def trans_line_run( trans, line_no ):
	"""Return the number of characters to the right edge of line line_no."""
	
	if line_no == 0:
		prev_epos = 0
	else:
		prev_epos = trans[line_no-1][3]
	l_pad, l_trim, r_trim, epos = trans[line_no]

	return epos - prev_epos + l_pad - l_trim - r_trim

def trans_line_skip( trans, line_no ):
	"""Return the number of characters to the left of line line_no."""
	
	return trans[line_no][0]
	

def split_attribute_list( attr_list, trans ):
	"""Return an attribute list split across lines according to trans."""

	# create a position list from the attribute list
	positions = [0]
	p = 0
	for attr, run in attr_list:
		p += run
		positions.append( p )
	
	# let the old code do the hard work
	coords = positions_to_coords( positions, trans )

	# one list per output line
	l = [[] for x in range(len(trans))]
	last_x = last_y = 0

	# turn coords back into attribute lists
	for (attr,run),(x,y) in zip( [(None,0)]+attr_list, coords ):
		if last_y == y:
			if last_x == x: 
				# run = 0, nothing to output
				continue
			if y >= len(l): # oddity from positions_to_coords
				continue
			l[y].append( (attr, x-last_x) )
		else:
			# handle tail of previous line
			run = trans_line_run( trans, last_y )
			if attr is not None and last_x < run:
				l[last_y].append( (attr, run-last_x) )
				
			# fill lines in between
			last_y += 1
			while attr is not None and last_y < y:
				skip = trans_line_skip( trans, last_y )
				run = trans_line_run( trans, last_y )
				if run > skip: 
					if skip:
						l[last_y].append( (None, skip) )
					l[last_y].append( (attr, run-skip) )
				last_y += 1
			
			# then start the new line
			skip = trans_line_skip( trans, y )
			if skip:
				l[y].append( (None, skip) )
			if x > skip:
				l[y].append( (attr, x-skip) )
		last_x, last_y = x, y

	return l


def fill_attribute_list( attr_list, width, attr ):
	"""Fill None items in attr list with an attribute."""

	o = []
	
	for line in attr_list:
		l = []
		col = 0
		for a, run in line:
			if a is None:
				a = attr
			l.append( (a, run) )
			col += run
		if col < width:
			l.append( (attr, width-col) )
		o.append( l )
	return o
	

def shift_translation_right( trans, shift, width ):
	l = []
	last = 0
	for l_pad, l_trim, r_trim, epos in trans:
		if shift <= l_trim:
			# shift satisfied by reducing l_trim
			l_trim -= shift
		else:
			l_pad = l_pad + shift - l_trim
			if l_pad > width: l_pad = width
			l_trim = 0
		
		if epos - last + l_pad - l_trim - r_trim > width:
			# shifted right side beyond width
			r_trim = epos - last + l_pad - l_trim - width

		last = epos
		l.append( (l_pad, l_trim, r_trim, epos) )
	return l
	
def shift_translation_left( trans, shift, width ):
	l = []
	last = 0
	for l_pad, l_trim, r_trim, epos in trans:
		if shift <= l_pad:
			# shift satisfied by reducing l_pad
			l_pad -= shift
		else:
			l_trim = l_trim + shift - l_pad
			if l_trim > epos - last: l_trim = epos - last
			l_pad = 0

		r_trim = 0
		if epos - last + l_pad - l_trim - r_trim > width:
			r_trim = epos - last + l_pad - l_trim - width
			
		last = epos
		l.append( (l_pad, l_trim, r_trim, epos) )
	
	# Assuming all translation shifting will occur on clipped
	# text, then every line but the last ends with a CR that
	# should be hidden.  This loop trims one character from all
	# but the last line in the translation:
	l_rm_cr = []
	last = 0
	for l_pad, l_trim, r_trim, epos in l[:-1]:
		if r_trim == 0 and l_trim < epos - last: r_trim = 1
		last = epos
		l_rm_cr.append( (l_pad, l_trim, r_trim, epos) )
	l_rm_cr.append( l[-1] )
	
	return l_rm_cr



class TagMarkupException( Exception ): pass

def decompose_tagmarkup( tm ):
	"""Return (text string, attribute list) for tagmarkup passed."""
	
	tl, al = _tagmarkup_recurse( tm, None )
	text = "".join(tl)
	
	if al and al[-1][0] is None:
		del al[-1]
		
	return text, al
	
def _tagmarkup_recurse( tm, attr ):
	"""Return (text list, attribute list) for tagmarkup passed.
	
	tm -- tagmarkup
	attr -- current attribute or None"""
	
	if type(tm) == type(""):
		# text
		return [tm], [(attr, len(tm))]
		
	if type(tm) == type([]):
		# for lists recurse to process each subelement
		rtl = [] 
		ral = []
		for element in tm:
			tl, al = _tagmarkup_recurse( element, attr )
			if ral:
				# merge attributes when possible
				last_attr, last_run = ral[-1]
				top_attr, top_run = al[0]
				if last_attr == top_attr:
					ral[-1] = (top_attr, last_run + top_run)
					del al[-1]
			rtl += tl
			ral += al
		return rtl, ral
		
	if type(tm) == type(()):
		# tuples mark a new attribute boundary
		if len(tm) != 2: 
			raise TagMarkupException, "Tuples must be in the form (attribute, tagmarkup): %s" % `tm`

		attr, element = tm
		return _tagmarkup_recurse( element, attr )
	
	raise TagMarkupException, "Invalid markup element: %s" % `tm`

