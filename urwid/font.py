#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Urwid BigText fonts
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

from __future__ import nested_scopes

import re

from escape import utf8decode, SAFE_ASCII_DEC_SPECIAL_RE
from util import apply_target_encoding, str_util
from canvas import TextCanvas

try: True # old python?
except: False, True = 0, 1

def separate_glyphs(gdata, height):
    """return (dictionary of glyphs, utf8 required)"""
    gl = gdata.split("\n")
    del gl[0]
    del gl[-1]
    for g in gl:
        assert "\t" not in g
    assert len(gl) == height+1, `gdata`
    key_line = gl[0]
    del gl[0]
    c = None # current character
    key_index = 0 # index into character key line
    end_col = 0 # column position at end of glyph
    start_col = 0 # column position at start of glyph
    jl = [0]*height # indexes into lines of gdata (gl)
    dout = {}
    utf8_required = False
    while True:
        if c is None:
            if key_index >= len(key_line):
                break
            c = key_line[key_index]
        if key_index < len(key_line) and key_line[key_index] == c:
            end_col += str_util.get_width(ord(c))
            key_index += 1
            continue
        out = []
        for k in range(height):
            l = gl[k]
            j = jl[k]
            y = 0
            fill = 0
            while y < end_col - start_col:
                if j >= len(l):
                    fill = end_col - start_col - y
                    break
                y += str_util.get_width(ord(l[j]))
                j += 1
            assert y + fill == end_col - start_col, \
                `y, fill, end_col`
            
            segment = l[jl[k]:j]
            if not SAFE_ASCII_DEC_SPECIAL_RE.match(segment):
                utf8_required = True
            
            out.append(segment + " " * fill)
            jl[k] = j

        start_col = end_col
        dout[c] = (y + fill, out)
        c = None
    return dout, utf8_required

_all_fonts = []
def get_all_fonts():
    """
    Return a list of (font name, font class) tuples.
    """
    return _all_fonts[:]

def add_font(name, cls):
    _all_fonts.append((name, cls))


class Font(object):
    def __init__(self):
        assert self.height
        assert self.data
        self.char = {}
        self.canvas = {}
        self.utf8_required = False
        for gdata in self.data:
            self.add_glyphs(gdata)
        

    def add_glyphs(self, gdata):
        d, utf8_required = separate_glyphs(gdata, self.height)
        self.char.update(d)
        self.utf8_required |= utf8_required

    def characters(self):
        l = self.char.keys()
        l.sort()
        return "".join(l)

    def char_width(self, c):
        if self.char.has_key(c):
            return self.char[c][0]
        return 0
    
    def char_data(self, c):
        return self.char[c][1]

    def render(self, c):
        if c in self.canvas:
            return self.canvas[c]
        width, l = self.char[c]
        tl = []
        csl = []
        for d in l:
            t, cs = apply_target_encoding(d)
            tl.append(t)
            csl.append(cs)
        canv = TextCanvas(tl, None, csl, maxcol=width, 
            check_width=False)
        self.canvas[c] = canv
        return canv
    

        
#safe_palette = utf8decode("┘┐┌└┼─├┤┴┬│")
#more_palette = utf8decode("═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬○")
#block_palette = utf8decode("▄#█#▀#▌#▐#▖#▗#▘#▙#▚#▛#▜#▝#▞#▟")


class Thin3x3Font(Font):
    height = 3
    data = [utf8decode("""
000111222333444555666777888999  !
┌─┐ ┐ ┌─┐┌─┐  ┐┌─ ┌─ ┌─┐┌─┐┌─┐  │
│ │ │ ┌─┘ ─┤└─┼└─┐├─┐  ┼├─┤└─┤  │
└─┘ ┴ └─ └─┘  ┴ ─┘└─┘  ┴└─┘ ─┘  .
"""), utf8decode(r"""
"###$$$%%%'*++,--.///:;==???[[\\\]]^__`
" ┼┼┌┼┐O /'         /.. _┌─┐┌ \   ┐^  `
  ┼┼└┼┐ /  * ┼  ─  / ., _ ┌┘│  \  │     
    └┼┘/ O    ,  ./       . └   \ ┘ ──
""")]
add_font("Thin 3x3",Thin3x3Font)

class Thin4x3Font(Font):
    height = 3
    data = Thin3x3Font.data + [utf8decode("""
0000111122223333444455556666777788889999  ####$$$$
┌──┐  ┐ ┌──┐┌──┐   ┐┌── ┌── ┌──┐┌──┐┌──┐   ┼─┼┌┼┼┐
│  │  │ ┌──┘  ─┤└──┼└──┐├──┐   ┼├──┤└──┤   ┼─┼└┼┼┐
└──┘  ┴ └── └──┘   ┴ ──┘└──┘   ┴└──┘ ──┘      └┼┼┘
""")]
add_font("Thin 4x3",Thin4x3Font)

class HalfBlock5x4Font(Font):
    height = 4
    data = [utf8decode("""
00000111112222233333444445555566666777778888899999  !!
▄▀▀▄  ▄█  ▄▀▀▄ ▄▀▀▄ ▄  █ █▀▀▀ ▄▀▀  ▀▀▀█ ▄▀▀▄ ▄▀▀▄   █ 
█  █   █    ▄▀   ▄▀ █▄▄█ █▄▄  █▄▄    ▐▌ ▀▄▄▀ ▀▄▄█   █ 
█  █   █  ▄▀   ▄  █    █    █ █  █   █  █  █    █   ▀ 
 ▀▀   ▀▀▀ ▀▀▀▀  ▀▀     ▀ ▀▀▀   ▀▀    ▀   ▀▀   ▀▀    ▀ 
"""), utf8decode('''
"""######$$$$$$%%%%%&&&&&((()))******++++++,,,-----..////:::;;
█▐▌ █ █  ▄▀█▀▄ ▐▌▐▌ ▄▀▄   █ █   ▄ ▄    ▄              ▐▌      
   ▀█▀█▀ ▀▄█▄    █  ▀▄▀  ▐▌ ▐▌ ▄▄█▄▄ ▄▄█▄▄    ▄▄▄▄    █  ▀  ▀ 
   ▀█▀█▀ ▄ █ █  ▐▌▄ █ ▀▄▌▐▌ ▐▌  ▄▀▄    █             ▐▌  ▀ ▄▀ 
    ▀ ▀   ▀▀▀   ▀ ▀  ▀▀   ▀ ▀              ▄▀      ▀ ▀        
'''), utf8decode(r"""
<<<<<=====>>>>>?????@@@@@@[[[[\\\\]]]]^^^^____```{{{{||}}}}~~~~''´´´
  ▄▀      ▀▄   ▄▀▀▄ ▄▀▀▀▄ █▀▀ ▐▌  ▀▀█ ▄▀▄     ▀▄  ▄▀ █ ▀▄   ▄  █ ▄▀ 
▄▀   ▀▀▀▀   ▀▄   ▄▀ █ █▀█ █    █    █            ▄▀  █  ▀▄ ▐▐▌▌     
 ▀▄  ▀▀▀▀  ▄▀    ▀  █ ▀▀▀ █    ▐▌   █             █  █  █    ▀      
   ▀      ▀      ▀   ▀▀▀  ▀▀▀   ▀ ▀▀▀     ▀▀▀▀     ▀ ▀ ▀            
"""), utf8decode('''
AAAAABBBBBCCCCCDDDDDEEEEEFFFFFGGGGGHHHHHIIJJJJJKKKKK
▄▀▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ █▀▀▀ █▀▀▀ ▄▀▀▄ █  █ █    █ █  █  
█▄▄█ █▄▄▀ █    █  █ █▄▄  █▄▄  █    █▄▄█ █    █ █▄▀    
█  █ █  █ █  ▄ █  █ █    █    █ ▀█ █  █ █ ▄  █ █ ▀▄  
▀  ▀ ▀▀▀   ▀▀  ▀▀▀  ▀▀▀▀ ▀     ▀▀  ▀  ▀ ▀  ▀▀  ▀  ▀  
'''), utf8decode('''
LLLLLMMMMMMNNNNNOOOOOPPPPPQQQQQRRRRRSSSSSTTTTT
█    █▄ ▄█ ██ █ ▄▀▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ ▄▀▀▄ ▀▀█▀▀
█    █ ▀ █ █▐▌█ █  █ █▄▄▀ █  █ █▄▄▀ ▀▄▄    █  
█    █   █ █ ██ █  █ █    █ ▌█ █  █ ▄  █   █
▀▀▀▀ ▀   ▀ ▀  ▀  ▀▀  ▀     ▀▀▌ ▀  ▀  ▀▀    ▀
'''), utf8decode('''
UUUUUVVVVVVWWWWWWXXXXXXYYYYYYZZZZZ
█  █ █   █ █   █ █   █ █   █ ▀▀▀█      
█  █ ▐▌ ▐▌ █ ▄ █  ▀▄▀   ▀▄▀   ▄▀  
█  █  █ █  ▐▌█▐▌ ▄▀ ▀▄   █   █    
 ▀▀    ▀    ▀ ▀  ▀   ▀   ▀   ▀▀▀▀     
'''), utf8decode('''
aaaaabbbbbcccccdddddeeeeeffffggggghhhhhiijjjjkkkkk
     █            █       ▄▀▀     █    ▄   ▄ █
 ▀▀▄ █▀▀▄ ▄▀▀▄ ▄▀▀█ ▄▀▀▄ ▀█▀ ▄▀▀▄ █▀▀▄ ▄   ▄ █ ▄▀    
▄▀▀█ █  █ █  ▄ █  █ █▀▀   █  ▀▄▄█ █  █ █   █ █▀▄   
 ▀▀▀ ▀▀▀   ▀▀   ▀▀▀  ▀▀   ▀   ▄▄▀ ▀  ▀ ▀ ▄▄▀ ▀  ▀  
'''), utf8decode('''
llmmmmmmnnnnnooooopppppqqqqqrrrrssssstttt
█                                     █  
█ █▀▄▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ ▄▀▀█ █▀▀ ▄▀▀▀ ▀█▀  
█ █ █ █ █  █ █  █ █  █ █  █ █    ▀▀▄  █
▀ ▀   ▀ ▀  ▀  ▀▀  █▀▀   ▀▀█ ▀   ▀▀▀    ▀
'''), utf8decode('''
uuuuuvvvvvwwwwwwxxxxxxyyyyyzzzzz
                           
█  █ █  █ █ ▄ █ ▀▄ ▄▀ █  █ ▀▀█▀
█  █ ▐▌▐▌ ▐▌█▐▌  ▄▀▄  ▀▄▄█ ▄▀   
 ▀▀   ▀▀   ▀ ▀  ▀   ▀  ▄▄▀ ▀▀▀▀
''')]
add_font("Half Block 5x4",HalfBlock5x4Font)

class HalfBlock6x5Font(Font):
    height = 5
    data = [utf8decode("""
000000111111222222333333444444555555666666777777888888999999  ..::////
▄▀▀▀▄  ▄█   ▄▀▀▀▄ ▄▀▀▀▄ ▄  █  █▀▀▀▀ ▄▀▀▀  ▀▀▀▀█ ▄▀▀▀▄ ▄▀▀▀▄         █
█   █   █       █     █ █  █  █     █        ▐▌ █   █ █   █     ▀  ▐▌
█   █   █     ▄▀    ▀▀▄ ▀▀▀█▀ ▀▀▀▀▄ █▀▀▀▄    █  ▄▀▀▀▄  ▀▀▀█     ▄  █
█   █   █   ▄▀    ▄   █    █      █ █   █   ▐▌  █   █     █       ▐▌
 ▀▀▀   ▀▀▀  ▀▀▀▀▀  ▀▀▀     ▀  ▀▀▀▀   ▀▀▀    ▀    ▀▀▀   ▀▀▀    ▀   ▀
""")]
add_font("Half Block 6x5",HalfBlock6x5Font)

class HalfBlockHeavy6x5Font(Font):
    height = 5
    data = [utf8decode("""
000000111111222222333333444444555555666666777777888888999999  ..::////
▄███▄  ▐█▌  ▄███▄ ▄███▄    █▌ █████ ▄███▄ █████ ▄███▄ ▄███▄         █▌
█▌ ▐█  ▀█▌  ▀  ▐█ ▀  ▐█ █▌ █▌ █▌    █▌       █▌ █▌ ▐█ █▌ ▐█     █▌ ▐█
█▌ ▐█   █▌    ▄█▀   ██▌ █████ ████▄ ████▄   ▐█  ▐███▌ ▀████        █▌
█▌ ▐█   █▌  ▄█▀   ▄  ▐█    █▌    ▐█ █▌ ▐█   █▌  █▌ ▐█    ▐█     █▌▐█
▀███▀  ███▌ █████ ▀███▀    █▌ ████▀ ▀███▀  ▐█   ▀███▀ ▀███▀   █▌  █▌
""")]
add_font("Half Block Heavy 6x5",HalfBlockHeavy6x5Font)

class Thin6x6Font(Font):
    height = 6
    data = [utf8decode("""
000000111111222222333333444444555555666666777777888888999999''
┌───┐   ┐   ┌───┐ ┌───┐    ┐  ┌───  ┌───  ┌───┐ ┌───┐ ┌───┐ │
│   │   │       │     │ ┌  │  │     │         │ │   │ │   │  
│ / │   │   ┌───┘    ─┤ └──┼─ └───┐ ├───┐     ┼ ├───┤ └───┤ 
│   │   │   │         │    │      │ │   │     │ │   │     │ 
└───┘   ┴   └───  └───┘    ┴   ───┘ └───┘     ┴ └───┘  ───┘ 

"""),utf8decode(r'''
!!   """######$$$$$$%%%%%%&&&&&&((()))******++++++
│    ││  ┌ ┌  ┌─┼─┐ ┌┐  /  ┌─┐   / \      
│       ─┼─┼─ │ │   └┘ /   │ │  │   │  \ /    │
│        │ │  └─┼─┐   /   ┌─\┘  │   │ ──X── ──┼── 
│       ─┼─┼─   │ │  / ┌┐ │  \, │   │  / \    │
.        ┘ ┘  └─┼─┘ /  └┘ └───\  \ /  

'''),utf8decode(r"""
,,-----..//////::;;<<<<=====>>>>??????@@@@@@
             /                  ┌───┐ ┌───┐
            /  . .   / ──── \       │ │┌──┤
  ────     /        /        \    ┌─┘ ││  │ 
          /    . ,  \  ────  /    │   │└──┘
,      . /           \      /     .   └───┘

"""),utf8decode(r"""
[[\\\\\\]]^^^____``{{||}}~~~~~~
┌ \     ┐ /\     \ ┌ │ ┐ 
│  \    │          │ │ │ ┌─┐
│   \   │          ┤ │ ├   └─┘
│    \  │          │ │ │ 
└     \ ┘    ────  └ │ ┘ 

"""),utf8decode("""
AAAAAABBBBBBCCCCCCDDDDDDEEEEEEFFFFFFGGGGGGHHHHHHIIJJJJJJ
┌───┐ ┬───┐ ┌───┐ ┬───┐ ┬───┐ ┬───┐ ┌───┐ ┬   ┬ ┬     ┬
│   │ │   │ │     │   │ │     │     │     │   │ │     │
├───┤ ├───┤ │     │   │ ├──   ├──   │ ──┬ ├───┤ │     │
│   │ │   │ │     │   │ │     │     │   │ │   │ │ ┬   │
┴   ┴ ┴───┘ └───┘ ┴───┘ ┴───┘ ┴     └───┘ ┴   ┴ ┴ └───┘

"""),utf8decode("""
KKKKKKLLLLLLMMMMMMNNNNNNOOOOOOPPPPPPQQQQQQRRRRRRSSSSSS
┬   ┬ ┬     ┌─┬─┐ ┬─┐ ┬ ┌───┐ ┬───┐ ┌───┐ ┬───┐ ┌───┐
│ ┌─┘ │     │ │ │ │ │ │ │   │ │   │ │   │ │   │ │
├─┴┐  │     │ │ │ │ │ │ │   │ ├───┘ │   │ ├─┬─┘ └───┐
│  └┐ │     │   │ │ │ │ │   │ │     │  ┐│ │ └─┐     │
┴   ┴ ┴───┘ ┴   ┴ ┴ └─┴ └───┘ ┴     └──┼┘ ┴   ┴ └───┘
                                       └
"""),utf8decode("""
TTTTTTUUUUUUVVVVVVWWWWWWXXXXXXYYYYYYZZZZZZ
┌─┬─┐ ┬   ┬ ┬   ┬ ┬   ┬ ┬   ┬ ┬   ┬ ┌───┐ 
  │   │   │ │   │ │   │ └┐ ┌┘ │   │   ┌─┘ 
  │   │   │ │   │ │ │ │  ├─┤  └─┬─┘  ┌┘  
  │   │   │ └┐ ┌┘ │ │ │ ┌┘ └┐   │   ┌┘    
  ┴   └───┘  └─┘  └─┴─┘ ┴   ┴   ┴   └───┘ 
                                        
"""),utf8decode("""
aaaaaabbbbbbccccccddddddeeeeeefffgggggghhhhhhiijjj
                              ┌─┐      
      │               │       │        │     .  .
┌───┐ ├───┐ ┌───┐ ┌───┤ ┌───┐ ┼  ┌───┐ ├───┐ ┐  ┐
┌───┤ │   │ │     │   │ ├───┘ │  │   │ │   │ │  │
└───┴ └───┘ └───┘ └───┘ └───┘ ┴  └───┤ ┴   ┴ ┴  │
                                 └───┘         ─┘
"""),utf8decode("""
kkkkkkllmmmmmmnnnnnnooooooppppppqqqqqqrrrrrssssss
                                
│     │                                   
│ ┌─  │ ┬─┬─┐ ┬───┐ ┌───┐ ┌───┐ ┌───┐ ┬──┐ ┌───┐
├─┴┐  │ │ │ │ │   │ │   │ │   │ │   │ │    └───┐
┴  └─ └ ┴   ┴ ┴   ┴ └───┘ ├───┘ └───┤ ┴    └───┘
                          │         │     
"""),utf8decode("""
ttttuuuuuuvvvvvvwwwwwwxxxxxxyyyyyyzzzzzz
                
 │                        
─┼─ ┬   ┬ ┬   ┬ ┬   ┬ ─┐ ┌─ ┬   ┬ ────┬
 │  │   │ └┐ ┌┘ │ │ │  ├─┤  │   │ ┌───┘
 └─ └───┴  └─┘  └─┴─┘ ─┘ └─ └───┤ ┴────
                            └───┘
""")]
add_font("Thin 6x6",Thin6x6Font)


class HalfBlock7x7Font(Font):
    height = 7
    data = [utf8decode("""
0000000111111122222223333333444444455555556666666777777788888889999999'''
 ▄███▄   ▐█▌   ▄███▄  ▄███▄     █▌ ▐█████▌ ▄███▄ ▐█████▌ ▄███▄  ▄███▄ ▐█
▐█   █▌  ▀█▌  ▐█   █▌▐█   █▌▐█  █▌ ▐█     ▐█         ▐█ ▐█   █▌▐█   █▌▐█
▐█ ▐ █▌   █▌       █▌   ▐██ ▐█████▌▐████▄ ▐████▄     █▌  █████  ▀████▌  
▐█ ▌ █▌   █▌     ▄█▀      █▌    █▌      █▌▐█   █▌   ▐█  ▐█   █▌     █▌  
▐█   █▌   █▌   ▄█▀   ▐█   █▌    █▌      █▌▐█   █▌   █▌  ▐█   █▌     █▌  
 ▀███▀   ███▌ ▐█████▌ ▀███▀     █▌ ▐████▀  ▀███▀   ▐█    ▀███▀  ▀███▀ 

"""),utf8decode('''
!!!   """""#######$$$$$$$%%%%%%%&&&&&&&(((())))*******++++++
▐█    ▐█ █▌ ▐█ █▌    █    ▄  █▌   ▄█▄    █▌▐█   ▄▄ ▄▄    
▐█    ▐█ █▌▐█████▌ ▄███▄ ▐█▌▐█   ▐█ █▌  ▐█  █▌  ▀█▄█▀   ▐█
▐█          ▐█ █▌ ▐█▄█▄▄  ▀ █▌    ███   █▌  ▐█ ▐█████▌ ████▌
▐█         ▐█████▌ ▀▀█▀█▌  ▐█ ▄  ███▌▄  █▌  ▐█  ▄█▀█▄   ▐█ 
            ▐█ █▌  ▀███▀   █▌▐█▌▐█  █▌  ▐█  █▌  ▀▀ ▀▀    
▐█                   █    ▐█  ▀  ▀██▀█▌  █▌▐█ 
                   
'''),utf8decode("""
,,,------.../////:::;;;<<<<<<<======>>>>>>>???????@@@@@@@
               █▌          ▄█▌      ▐█▄     ▄███▄  ▄███▄       
              ▐█ ▐█ ▐█   ▄█▀  ▐████▌  ▀█▄  ▐█   █▌▐█ ▄▄█▌   
   ▐████▌     █▌       ▐██              ██▌    █▌ ▐█▐█▀█▌
             ▐█  ▐█ ▐█   ▀█▄  ▐████▌  ▄█▀     █▌  ▐█▐█▄█▌
             █▌     ▀      ▀█▌      ▐█▀           ▐█ ▀▀▀    
▐█       ▐█ ▐█                                █▌   ▀███▀ 
▀                          
"""),utf8decode(r"""
[[[[\\\\\]]]]^^^^^^^_____```{{{{{|||}}}}}~~~~~~~´´´
▐██▌▐█   ▐██▌  ▐█▌       ▐█    █▌▐█ ▐█           █▌  
▐█   █▌    █▌ ▐█ █▌       █▌  █▌ ▐█  ▐█   ▄▄    ▐█ 
▐█   ▐█    █▌▐█   █▌         ▄█▌ ▐█  ▐█▄ ▐▀▀█▄▄▌
▐█    █▌   █▌                ▀█▌ ▐█  ▐█▀     ▀▀
▐█    ▐█   █▌                 █▌ ▐█  ▐█ 
▐██▌   █▌▐██▌       █████      █▌▐█ ▐█  
                                      
"""),utf8decode("""
AAAAAAABBBBBBBCCCCCCCDDDDDDDEEEEEEEFFFFFFFGGGGGGGHHHHHHHIIIIJJJJJJJ
 ▄███▄ ▐████▄  ▄███▄ ▐████▄ ▐█████▌▐█████▌ ▄███▄ ▐█   █▌ ██▌     █▌ 
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█     ▐█   █▌ ▐█      █▌  
▐█████▌▐█████ ▐█     ▐█   █▌▐████  ▐████  ▐█     ▐█████▌ ▐█      █▌
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█  ██▌▐█   █▌ ▐█      █▌
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█   █▌▐█   █▌ ▐█ ▐█   █▌
▐█   █▌▐████▀  ▀███▀ ▐████▀ ▐█████▌▐█      ▀███▀ ▐█   █▌ ██▌ ▀███▀ 
                     
"""),utf8decode("""
KKKKKKKLLLLLLLMMMMMMMMNNNNNNNOOOOOOOPPPPPPPQQQQQQQRRRRRRRSSSSSSS
▐█   █▌▐█      ▄█▌▐█▄ ▐██  █▌ ▄███▄ ▐████▄  ▄███▄ ▐████▄  ▄███▄ 
▐█  █▌ ▐█     ▐█ ▐▌ █▌▐██▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█     
▐█▄█▌  ▐█     ▐█ ▐▌ █▌▐█▐█ █▌▐█   █▌▐████▀ ▐█   █▌▐█████  ▀███▄ 
▐█▀█▌  ▐█     ▐█    █▌▐█ █▌█▌▐█   █▌▐█     ▐█   █▌▐█   █▌     █▌
▐█  █▌ ▐█     ▐█    █▌▐█ ▐██▌▐█   █▌▐█     ▐█ █▌█▌▐█   █▌     █▌
▐█   █▌▐█████▌▐█    █▌▐█  ██▌ ▀███▀ ▐█      ▀███▀ ▐█   █▌ ▀███▀ 
                                               ▀▀ 
"""),utf8decode("""
TTTTTTTUUUUUUUVVVVVVVWWWWWWWWXXXXXXXYYYYYYYZZZZZZZ
 █████▌▐█   █▌▐█   █▌▐█    █▌▐█   █▌ █▌  █▌▐█████▌ 
   █▌  ▐█   █▌ █▌ ▐█ ▐█    █▌ ▐█ █▌  ▐█ ▐█     █▌    
   █▌  ▐█   █▌ ▐█ █▌ ▐█    █▌  ▐█▌    ▐██     █▌        
   █▌  ▐█   █▌  ███  ▐█ ▐▌ █▌  ███     █▌    █▌
   █▌  ▐█   █▌  ▐█▌  ▐█ ▐▌ █▌ █▌ ▐█    █▌   █▌
   █▌   ▀███▀    █    ▀█▌▐█▀ ▐█   █▌   █▌  ▐█████▌       
                                               
"""),utf8decode("""
aaaaaaabbbbbbbcccccccdddddddeeeeeeefffffggggggghhhhhhhiiijjjj
       ▐█                 █▌         ▄█▌       ▐█      █▌  █▌
       ▐█                 █▌        ▐█         ▐█            
 ▄███▄ ▐████▄  ▄███▄  ▄████▌ ▄███▄ ▐███  ▄███▄ ▐████▄ ▐█▌ ▐█▌
  ▄▄▄█▌▐█   █▌▐█     ▐█   █▌▐█▄▄▄█▌ ▐█  ▐█   █▌▐█   █▌ █▌  █▌   
▐█▀▀▀█▌▐█   █▌▐█     ▐█   █▌▐█▀▀▀   ▐█  ▐█▄▄▄█▌▐█   █▌ █▌  █▌
 ▀████▌▐████▀  ▀███▀  ▀████▌ ▀███▀  ▐█    ▀▀▀█▌▐█   █▌ █▌  █▌
                                         ▀███▀           ▐██ 
"""),utf8decode("""
kkkkkkkllllmmmmmmmmnnnnnnnooooooopppppppqqqqqqqrrrrrrsssssss
▐█      ██                                                  
▐█      ▐█                                                  
▐█  ▄█▌ ▐█  ▄█▌▐█▄ ▐████▄  ▄███▄ ▐████▄  ▄████▌ ▄███▌ ▄███▄ 
▐█▄█▀   ▐█ ▐█ ▐▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█    ▐█▄▄▄  
▐█▀▀█▄  ▐█ ▐█ ▐▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█      ▀▀▀█▌
▐█   █▌ ▐█▌▐█    █▌▐█   █▌ ▀███▀ ▐████▀  ▀████▌▐█     ▀███▀ 
                                 ▐█          █▌
"""),utf8decode("""
tttttuuuuuuuvvvvvvvwwwwwwwwxxxxxxxyyyyyyyzzzzzzz
  █▌
  █▌
 ███▌▐█   █▌▐█   █▌▐█    █▌▐█   █▌▐█   █▌▐█████▌  
  █▌ ▐█   █▌ █▌ ▐█ ▐█    █▌ ▀█▄█▀ ▐█   █▌   ▄█▀ 
  █▌ ▐█   █▌  ███  ▐█ ▐▌ █▌ ▄█▀█▄ ▐█▄▄▄█▌ ▄█▀
  █▌  ▀███▀   ▐█▌   ▀█▌▐█▀ ▐█   █▌  ▀▀▀█▌▐█████▌
                                   ▀███▀ 
""")]
add_font("Half Block 7x7",HalfBlock7x7Font)


if __name__ == "__main__":
    l = get_all_fonts()
    all_ascii = "".join([chr(x) for x in range(32, 127)])
    print "Available Fonts:     (U) = UTF-8 required"
    print "----------------"
    for n,cls in l:
        f = cls()
        u = ""
        if f.utf8_required:
            u = "(U)"
        print ("%-20s %3s " % (n,u)),
        c = f.characters()
        if c == all_ascii:
            print "Full ASCII"
        elif c.startswith(all_ascii):
            print "Full ASCII + " + c[len(all_ascii):]
        else:
            print "Characters: " + c
