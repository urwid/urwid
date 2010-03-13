#!/usr/bin/python

"""
The crystalfontz 635 has these characters in ROM:

....X. ...... ......
...XX. .XXXXX ..XXX.
..XXX. .XXXXX .XXXXX
.XXXX. .XXXXX .XXXXX
..XXX. .XXXXX .XXXXX
...XX. .XXXXX ..XXX.
....X. ...... ......
...... ...... ......
  0x11   0xd0   0xbb

By adding the characters in CGRAM below we can use them as part of a 
horizontal slider control, selected check box and selected radio button
respectively.
"""

import urwid.lcd_display

CGRAM = """
...... ...... ...... ...... ..X... ...... ...... ...... 
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. .....X 
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X ....XX 
...... XX.... XXXX.. XXXXXX X.XXXX .X...X .X...X .X.XX. 
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X .XXX.. 
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. ..X... 
...... ...... ...... ...... ..X... ...... ...... ...... 
...... ...... ...... ...... ...... ...... ...... ...... 
"""

def program_cgram(screen):
    """
    Load the character data
    """
    # convert .'s and X's above into integer data
    cbuf = [list() for x in range(8)]
    for row in CGRAM.strip().split('\n'):
        rowsegments = row.strip().split()
        for num, r in enumerate(rowsegments):
            accum = 0
            for c in r:
                accum = (accum << 1) + (c == 'X')
            cbuf[num].append(accum)

    for num, cdata in enumerate(cbuf):
        screen.program_cgram(num, cdata)



txt = urwid.Edit("",
    "hello\n\x11\x03\x00\x02\x01\x00\x04\n\xd0\x05\xbb\x06\x07", 
    align=urwid.CENTER, multiline=True)
screen = urwid.lcd_display.CF635Screen('/dev/ttyUSB0')
program_cgram(screen)
# FIXME: want screen to know it is in narrow mode, or better yet, 
# do the unicode conversion for us
urwid.set_encoding('narrow')


def unhandled(i):
    print i

loop = urwid.MainLoop(urwid.Filler(txt), 
    screen=screen,
    unhandled_input=unhandled)

loop.run()
