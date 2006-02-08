#!/usr/bin/python
#
# Urwid unicode character processing tables
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

# GENERATED DATA
# generated from 
# http://www.unicode.org/Public/4.0-Update/EastAsianWidth-4.0.0.txt

widths = [
	(126, 1),
	(159, 0),
	(687, 1),
	(710, 0),
	(711, 1),
	(727, 0),
	(733, 1),
	(879, 0),
	(1154, 1),
	(1161, 0),
	(4347, 1),
	(4447, 2),
	(7467, 1),
	(7521, 0),
	(8369, 1),
	(8426, 0),
	(9000, 1),
	(9002, 2),
	(11021, 1),
	(12350, 2),
	(12351, 1),
	(12438, 2),
	(12442, 0),
	(19893, 2),
	(19967, 1),
	(55203, 2),
	(63743, 1),
	(64106, 2),
	(65039, 1),
	(65059, 0),
	(65131, 2),
	(65279, 1),
	(65376, 2),
	(65500, 1),
	(65510, 2),
	(120831, 1),
	(262141, 2),
	(1114109, 1),
]

# ACCESSOR FUNCTIONS

def get_width( o ):
	"""Return the screen column width for unicode ordinal o."""
	global widths
	for num, wid in widths:
		if o <= num:
			return wid
	return 1

def decode_one( text, pos ):
	"""Return (ordinal at pos, next position) for UTF-8 encoded text."""
	b1 = ord(text[pos])
	if not b1 & 0x80: 
		return b1, pos+1
	error = ord("?"), pos+1
	lt = len(text)
	remain = lt-pos
	if lt < 2:
		return error
	if b1 & 0xe0 == 0xc0:
		b2 = ord(text[pos+1])
		if b2 & 0xc0 != 0x80:
			return error
		o = ((b1&0x1f)<<6)|(b2&0x3f)
		if o < 0x80:
			return error
		return o, pos+2
	if lt < 3:
		return error
	if b1 & 0xf0 == 0xe0:
		b2 = ord(text[pos+1])
		if b2 & 0xc0 != 0x80:
			return error
		b3 = ord(text[pos+2])
		if b3 & 0xc0 != 0x80:
			return error
		o = ((b1&0x0f)<<12)|((b2&0x3f)<<6)|(b3&0x3f)
		if o < 0x800:
			return error
		return o, pos+3
	if lt < 4:
		return error
	if b1 & 0xf8 == 0xf0:
		b2 = ord(text[pos+1])
		if b2 & 0xc0 != 0x80:
			return error
		b3 = ord(text[pos+2])
		if b3 & 0xc0 != 0x80:
			return error
		b4 = ord(text[pos+2])
		if b4 & 0xc0 != 0x80:
			return error
		o = ((b1&0x07)<<18)|((b2&0x3f)<<12)|((b3&0x3f)<<6)|(b4&0x3f)
		if o < 0x10000:
			return error
		return o, pos+4
	return error

def decode_one_right( text, pos):
	"""
	Return (ordinal at pos, next position) for UTF-8 encoded text.
	pos is assumed to be on the trailing byte of a utf-8 sequence."""
	error = ord("?"), pos-1
	p = pos
	while p >= 0:
		if ord(text[p])&0xc0 != 0x80:
			o, next = decode_one( text, p )
			return o, p-1
		p -=1
		if p == p-4:
			return error

# TABLE GENERATION CODE

def process_east_asian_width():
	import sys
	out = []
	last = None
	for line in sys.stdin.readlines():
		if line[:1] == "#": continue
		line = line.strip()
		hex,rest = line.split(";",1)
		wid,rest = rest.split(" # ",1)
		word1 = rest.split(" ",1)[0]

		if "." in hex:
			hex = hex.split("..")[1]
		num = int(hex, 16)

		if word1 in ("COMBINING","MODIFIER","<control>"):
			l = 0
		elif wid in ("W", "F"):
			l = 2
		else:
			l = 1

		if last is None:
			out.append((0, l))
			last = l
		
		if last == l:
			out[-1] = (num, l)
		else:
			out.append( (num, l) )
			last = l

	print "widths = ["
	for o in out[1:]:  # treat control characters same as ascii
		print "\t"+`o`+","
	print "]"
		
if __name__ == "__main__":
	process_east_asian_width()

