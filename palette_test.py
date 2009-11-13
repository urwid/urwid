#!/usr/bin/python
#
# Urwid Palette Test.  Showing off highcolor support
#    Copyright (C) 2004-2009  Ian Ward
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
Palette test.  Shows the available foreground and background settings
in monochrome, 16 color, 88 color and 256 color modes.
"""

import re
import sys

import urwid
import urwid.raw_display

CHART_256 = """
brown__   dark_red_   dark_magenta_   dark_blue_   dark_cyan_   dark_green_
yellow_   light_red   light_magenta   light_blue   light_cyan   light_green

              #00f#06f#08f#0af#0df#0ff        black_______    dark_gray___   
            #60f#00d#06d#08d#0ad#0dd#0fd        light_gray__    white_______
          #80f#60d#00a#06a#08a#0aa#0da#0fa        
        #a0f#80d#60a#008#068#088#0a8#0d8#0f8        
      #d0f#a0d#80d#608#006#066#086#0a6#0d6#0f6
    #f0f#d0d#a0a#808#606#000#060#080#0a0#0d0#0f0#0f6#0f8#0fa#0fd#0ff
      #f0d#d0a#a08#806#600#660#680#6a0#6d0#6f0#6f6#6f8#6fa#6fd#6ff#0df
        #f0a#d08#a06#800#860#880#8a0#8d0#8f0#8f6#8f8#8fa#8fd#8ff#6df#0af
          #f08#d06#a00#a60#a80#aa0#ad0#af0#af6#af8#afa#afd#aff#8df#6af#08f
            #f06#d00#d60#d80#da0#dd0#df0#df6#df8#dfa#dfd#dff#adf#8af#68f#06f
              #f00#f60#f80#fa0#fd0#ff0#ff6#ff8#ffa#ffd#fff#ddf#aaf#88f#66f#00f
                                    #fd0#fd6#fd8#fda#fdd#fdf#daf#a8f#86f#60f
      #66d#68d#6ad#6dd                #fa0#fa6#fa8#faa#fad#faf#d8f#a6f#80f
    #86d#66a#68a#6aa#6da                #f80#f86#f88#f8a#f8d#f8f#d6f#a0f
  #a6d#86a#668#688#6a8#6d8                #f60#f66#f68#f6a#f6d#f6f#d0f
#d6d#a6a#868#666#686#6a6#6d6#6d8#6da#6dd    #f00#f06#f08#f0a#f0d#f0f
  #d6a#a68#866#886#8a6#8d6#8d8#8da#8dd#6ad       
    #d68#a66#a86#aa6#ad6#ad8#ada#add#8ad#68d   
      #d66#d86#da6#dd6#dd8#dda#ddd#aad#88d#66d        g78_g82_g85_g89_g93_g100  
                    #da6#da8#daa#dad#a8d#86d        g52_g58_g62_g66_g70_g74_
      #88a#8aa        #d86#d88#d8a#d8d#a6d        g27_g31_g35_g38_g42_g46_g50_
    #a8a#888#8a8#8aa    #d66#d68#d6a#d6d        g0__g3__g7__g11_g15_g19_g23_
      #a88#aa8#aaa#88a                        
            #a88#a8a
"""                    

CHART_88 = """
brown__   dark_red_   dark_magenta_   dark_blue_   dark_cyan_   dark_green_
yellow_   light_red   light_magenta   light_blue   light_cyan   light_green

      #00f#08f#0cf#0ff            black_______    dark_gray___             
    #80f#00c#08c#0cc#0fc            light_gray__    white_______           
  #c0f#80c#008#088#0c8#0f8
#f0f#c0c#808#000#080#0c0#0f0#0f8#0fc#0ff            #88c#8cc        
  #f0c#c08#800#880#8c0#8f0#8f8#8fc#8ff#0cf        #c8c#888#8c8#8cc   
    #f08#c00#c80#cc0#cf0#cf8#cfc#cff#8cf#08f        #c88#cc8#ccc#88c
      #f00#f80#fc0#ff0#ff8#ffc#fff#ccf#88f#00f            #c88#c8c        
                    #fc0#fc8#fcc#fcf#c8f#80f    
                      #f80#f88#f8c#f8f#c0f        g62_g74_g82_g89_g100  
                        #f00#f08#f0c#f0f        g0__g19_g35_g46_g52
"""

CHART_16 = """
brown__   dark_red_   dark_magenta_   dark_blue_   dark_cyan_   dark_green_
yellow_   light_red   light_magenta   light_blue   light_cyan   light_green

black_______    dark_gray___    light_gray__    white_______           
"""

ATTR_RE = re.compile("(?P<whitespace>[ \n]*)(?P<entry>[^ \n]+)")
SHORT_ATTR = 4 # length of short high-colour descriptions which may
# be packed one after the next

def parse_chart(chart, convert):
    """
    Convert string chart into text markup with the correct attributes.

    chart -- palette chart as a string
    convert -- function that converts a single palette entry to an
        (attr, text) tuple, or None if no match is found
    """
    out = []
    for match in re.finditer(ATTR_RE, chart):
        if match.group('whitespace'):
            out.append(match.group('whitespace'))
        entry = match.group('entry')
        entry = entry.replace("_", " ")
        while entry:
            # try the first four characters
            attrtext = convert(entry[:SHORT_ATTR])
            if attrtext:
                elen = SHORT_ATTR
                entry = entry[SHORT_ATTR:].strip()
            else: # try the whole thing
                attrtext = convert(entry.strip())
                assert attrtext, "Invalid palette entry: %r" % entry
                elen = len(entry)
                entry = ""
            attr, text = attrtext
            out.append((attr, text.ljust(elen)))
    return out
            
def foreground_chart(chart, background, colors):
    """
    Create text markup for a foreground colour chart

    chart -- palette chart as string
    background -- colour to use for background of chart
    colors -- number of colors (88 or 256)
    """
    def convert_foreground(entry):
        try:
            attr = urwid.AttrSpec(entry, background, colors)
        except urwid.AttrSpecError:
            return None
        return attr, entry
    return parse_chart(chart, convert_foreground)

def background_chart(chart, foreground, colors):
    """
    Create text markup for a background colour chart

    chart -- palette chart as string
    foreground -- colour to use for foreground of chart
    colors -- number of colors (88 or 256)

    This will remap 8 <= colour < 16 to high-colour versions
    in the hopes of greater compatibility
    """
    def convert_background(entry):
        try:
            attr = urwid.AttrSpec(foreground, entry, colors)
        except urwid.AttrSpecError:
            return None
        # fix 8 <= colour < 16
        if colors > 16 and attr.background_basic and \
            attr.background_number >= 8:
            # use high-colour with same number
            entry = 'h%d'%attr.background_number
            attr = urwid.AttrSpec(foreground, entry, colors)
        return attr, entry
    return parse_chart(chart, convert_background)


def main():
    palette = [
        ('header', 'black,underline', 'light gray', 'standout,underline',
            'black,underline', '#88a'),
        ('panel', 'light gray', 'dark blue', '',
            '#ffd', '#00a'),
        ('focus', 'light gray', 'dark cyan', 'standout',
            '#ff8', '#806'),
        ]

    screen = urwid.raw_display.Screen()
    screen.register_palette(palette)

    lb = urwid.SimpleListWalker([])
    chart_offset = None  # offset of chart in lb list

    mode_radio_buttons = []
    chart_radio_buttons = []

    def fcs(widget):
        # wrap widgets that can take focus
        return urwid.AttrMap(widget, None, 'focus')

    def set_mode(colors, is_foreground_chart):
        # set terminal mode and redraw chart
        screen.set_terminal_properties(colors)
        screen.reset_default_terminal_palette()

        chart_fn = (background_chart, foreground_chart)[is_foreground_chart]
        if colors == 1:
            lb[chart_offset] = urwid.Divider()
        else:
            chart = {16: CHART_16, 88: CHART_88, 256: CHART_256}[colors]
            txt = chart_fn(chart, 'default', colors)
            lb[chart_offset] = urwid.Text(txt, wrap='clip')

    def on_mode_change(rb, state, colors):
        # if this radio button is checked
        if state:
            is_foreground_chart = chart_radio_buttons[0].state
            set_mode(colors, is_foreground_chart)
            
    def mode_rb(text, colors, state=False):
        # mode radio buttons
        rb = urwid.RadioButton(mode_radio_buttons, text, state)
        urwid.connect_signal(rb, 'change', on_mode_change, colors)
        return fcs(rb)

    def on_chart_change(rb, state):
        # handle foreground check box state change
        set_mode(screen.colors, state)
        
    def click_exit(button):
        raise urwid.ExitMainLoop()
    
    lb.extend([
        urwid.AttrMap(urwid.Text("Urwid Palette Test"), 'header'),
        urwid.AttrMap(urwid.Columns([
            urwid.Pile([
                mode_rb("Monochrome", 1),
                mode_rb("16-Color", 16, True),
                mode_rb("88-Color", 88),
                mode_rb("256-Color", 256),]),
            urwid.Pile([
                fcs(urwid.RadioButton(chart_radio_buttons,
                    "Foreground Colors", True, on_chart_change)),
                fcs(urwid.RadioButton(chart_radio_buttons,
                    "Background Colors")),
                urwid.Divider(),
                fcs(urwid.Button("Exit", click_exit)),
                ]),
            ]),'panel')
        ])

    chart_offset = len(lb)
    lb.extend([
        urwid.Divider() # placeholder for the chart
        ])

    set_mode(16, True) # displays the chart
    
    def unhandled_input(key):
        if key in ('Q','q','esc'):
            raise urwid.ExitMainLoop()

    urwid.MainLoop(urwid.ListBox(lb), screen=screen,
        unhandled_input=unhandled_input).run()

if __name__ == "__main__":
    main()


