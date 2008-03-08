#!/usr/bin/python
# Urwid common display code
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

import sys
import termios

from util import int_scale

_BASIC_START = 0 # first index of basic colour aliases
_CUBE_START = 16 # first index of colour cube
_CUBE_SIZE_256 = 6 # one side of the colour cube
_GRAY_SIZE_256 = 24
_GRAY_START_256 = _CUBE_SIZE_256 ** 3 + _CUBE_START
_CUBE_WHITE_256 = _GRAY_START_256 -1
_CUBE_SIZE_88 = 4
_GRAY_SIZE_88 = 8
_GRAY_START_88 = _CUBE_SIZE_88 ** 3 + _CUBE_START
_CUBE_WHITE_88 = _GRAY_START_88 -1
_CUBE_BLACK = _CUBE_START

# values copied from xterm 256colres.h:
_CUBE_STEPS_256 = [0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff]
_GRAY_STEPS_256 = [0x08, 0x12, 0x1c, 0x26, 0x30, 0x3a, 0x44, 0x4e, 0x58, 0x62,
    0x6c, 0x76, 0x80, 0x84, 0x94, 0x9e, 0xa8, 0xb2, 0xbc, 0xc6, 0xd0,
    0xda, 0xe4, 0xee]
# values copied from xterm 88colres.h:
_CUBE_STEPS_88 = [0x00, 0x8b, 0xcd, 0xff]
_GRAY_STEPS_88 = [0x2e, 0x5c, 0x73, 0x8b, 0xa2, 0xb9, 0xd0, 0xe7]
# values copied from X11/rgb.txt and XTerm-col.ad:
_BASIC_COLOURS = [(0,0,0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
    (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
    (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0x5c, 0x5c, 0xff), (255, 0, 255), (0, 255, 255), (255, 255, 255)]


_FG_COLOUR_MASK = 0x000000ff
_BG_COLOUR_MASK = 0x0000ff00
_FG_BASIC_COLOUR = 0x00010000
_FG_HIGH_COLOUR = 0x00020000
_BG_BASIC_COLOUR = 0x00040000
_BG_HIGH_COLOUR = 0x00080000
_BG_SHIFT = 8
_HIGH_88_COLOUR = 0x00100000
_STANDOUT = 0x02000000
_UNDERLINE = 0x04000000
_BOLD = 0x08000000
_FG_MASK = (_FG_COLOUR_MASK | _FG_BASIC_COLOUR | _FG_HIGH_COLOUR |
    _STANDOUT | _UNDERLINE | _BOLD)
_BG_MASK = _BG_COLOUR_MASK | _BG_BASIC_COLOUR | _BG_HIGH_COLOUR

_BASIC_COLOURS = [
    'black',
    'dark red',
    'dark green',
    'brown',
    'dark blue',
    'dark magenta',
    'dark cyan',
    'light gray',
    'dark gray',
    'light red',
    'light green',
    'yellow',
    'light blue',
    'light magenta',
    'light cyan',
    'white',
]

_ATTRIBUTES = {
    'bold': _BOLD,
    'underline': _UNDERLINE,
    'standout': _STANDOUT,
}

def _value_lookup_table(values, size):
    """
    Generate a lookup table for finding the closest item in values.
    Lookup returns (index into values)+1
    
    values -- list of values in ascending order, all < size
    size -- size of lookup table and maximum value
    
    >>> _value_lookup_table([0, 7, 9], 10)
    [0, 0, 0, 0, 1, 1, 1, 1, 2, 2]
    """

    middle_values = [0] + [(values[i] + values[i + 1] + 1) / 2 
        for i in range(len(values) - 1)] + [size]
    lookup_table = []
    for i in range(len(middle_values)-1):
        count = middle_values[i + 1] - middle_values[i]
        lookup_table.extend([i] * count)
    return lookup_table

_CUBE_256_LOOKUP = _value_lookup_table(_CUBE_STEPS_256, 256)
_GRAY_256_LOOKUP = _value_lookup_table([0] + _GRAY_STEPS_256 + [0xff], 256)
_CUBE_88_LOOKUP = _value_lookup_table(_CUBE_STEPS_88, 256)
_GRAY_88_LOOKUP = _value_lookup_table([0] + _GRAY_STEPS_88 + [0xff], 256)

# convert steps to values that will be used by string versions of the colours
# 1 hex digit for rgb and 0..100 for grayscale
_CUBE_STEPS_256_16 = [int_scale(n, 0x100, 0x10) for n in _CUBE_STEPS_256]
_GRAY_STEPS_256_101 = [int_scale(n, 0x100, 101) for n in _GRAY_STEPS_256]
_CUBE_STEPS_88_16 = [int_scale(n, 0x100, 0x10) for n in _CUBE_STEPS_88]
_GRAY_STEPS_88_101 = [int_scale(n, 0x100, 101) for n in _GRAY_STEPS_88]

# create lookup tables for 1 hex digit rgb and 0..100 for grayscale values
_CUBE_256_LOOKUP_16 = [_CUBE_256_LOOKUP[int_scale(n, 16, 0x100)]
    for n in range(16)]
_GRAY_256_LOOKUP_101 = [_GRAY_256_LOOKUP[int_scale(n, 101, 0x100)]
    for n in range(101)]
_CUBE_88_LOOKUP_16 = [_CUBE_88_LOOKUP[int_scale(n, 16, 0x100)]
    for n in range(16)]
_GRAY_88_LOOKUP_101 = [_GRAY_88_LOOKUP[int_scale(n, 101, 0x100)]
    for n in range(101)]


# The functions _gray_num_256() and _gray_num_88() do not include the gray 
# values from the colour cube so that the gray steps are an even width.  
# The colour cube grays are available by using the rgb functions.  Pure 
# white and black are taken from the colour cube, since the gray range does 
# not include them, and the basic colours are more likely to have been 
# customized by an end-user.


def _gray_num_256(gnum):
    """Return ths colour number for gray number gnum.

    Colour cube black and white are returned for 0 and %d respectively
    since those values aren't included in the gray scale.

    """ % (_GRAY_SIZE_256+1)
    # grays start from index 1
    gnum -= 1

    if gnum < 0:
        return _CUBE_BLACK
    if gnum >= _GRAY_SIZE_256:
        return _CUBE_WHITE_256
    return _GRAY_START_256 + gnum


def _gray_num_88(gnum):
    """Return ths colour number for gray number gnum.

    Colour cube black and white are returned for 0 and %d respectively
    since those values aren't included in the gray scale.

    """ % (_GRAY_SIZE_88+1)
    # gnums start from index 1
    gnum -= 1

    if gnum < 0:
        return _CUBE_BLACK
    if gnum >= _GRAY_SIZE_88:
        return _CUBE_WHITE_88
    return _GRAY_START_88 + gnum


def _colour_desc_256(num):
    """
    Return a string description of colour number num.
    0..15 -> 'h0'..'h15' basic colours (as high-colours)
    16..231 -> '#000'..'#fff' colour cube colours
    232..255 -> 'g3'..'g93' grays

    >>> _colour_desc_256(15)
    'h15'
    >>> _colour_desc_256(16)
    '#000'
    >>> _colour_desc_256(17)
    '#006'
    >>> _colour_desc_256(230)
    '#ffd'
    >>> _colour_desc_256(233)
    'g7'
    >>> _colour_desc_256(234)
    'g11'

    """
    assert num > 0 and num < 256
    if num < _CUBE_START:
        return 'h%d' % num
    if num < _GRAY_START_256:
        num -= _CUBE_START
        b, num = num % _CUBE_SIZE_256, num / _CUBE_SIZE_256
        g, num = num % _CUBE_SIZE_256, num / _CUBE_SIZE_256
        r = num % _CUBE_SIZE_256
        return '#%x%x%x' % (_CUBE_STEPS_256_16[r], _CUBE_STEPS_256_16[g],
            _CUBE_STEPS_256_16[b])
    return 'g%d' % _GRAY_STEPS_256_101[num - _GRAY_START_256]

def _colour_desc_88(num):
    """
    Return a string description of colour number num.
    0..15 -> 'h0'..'h15' basic colours (as high-colours)
    16..79 -> '#000'..'#fff' colour cube colours
    80..87 -> 'g18'..'g90' grays
    
    >>> _colour_desc_88(15)
    'h15'
    >>> _colour_desc_88(16)
    '#000'
    >>> _colour_desc_88(17)
    '#008'
    >>> _colour_desc_88(78)
    '#ffc'
    >>> _colour_desc_88(81)
    'g36'
    >>> _colour_desc_88(82)
    'g45'

    """
    assert num > 0 and num < 88
    if num < _CUBE_START:
        return 'h%d' % num
    if num < _GRAY_START_88:
        num -= _CUBE_START
        b, num = num % _CUBE_SIZE_88, num / _CUBE_SIZE_88
        g, r= num % _CUBE_SIZE_88, num / _CUBE_SIZE_88
        return '#%x%x%x' % (_CUBE_STEPS_88_16[r], _CUBE_STEPS_88_16[g],
            _CUBE_STEPS_88_16[b])
    return 'g%d' % _GRAY_STEPS_88_101[num - _GRAY_START_88]

def _parse_colour_256(desc):
    """
    Return a colour number for the description desc.
    'h0'..'h255' -> 0..255 actual colour number
    '#000'..'#fff' -> 16..231 colour cube colours
    'g0'..'g100' -> 16, 232..255, 231 grays and colour cube black/white
    'g#00'..'g#ff' -> 16, 232...255, 231 gray and colour cube black/white
    
    Returns None if desc is invalid.

    >>> _parse_colour_256('h142')
    142
    >>> _parse_colour_256('#f00')
    196
    >>> _parse_colour_256('g100')
    231
    >>> _parse_colour_256('g#80')
    244
    """
    if len(desc) > 4:
        # keep the length within reason before parsing
        return None
    try:
        if desc.startswith('h'):
            # high-colour number
            num = int(desc[1:], 10)
            if num < 0 or num > 255:
                return None
            return num

        if desc.startswith('#') and len(desc) == 4:
            # colour-cube coordinates
            rgb = int(desc[1:], 16)
            if rgb < 0:
                return None
            b, rgb = rgb % 16, rgb / 16
            g, r = rgb % 16, rgb / 16
            # find the closest rgb values
            r = _CUBE_256_LOOKUP_16[r]
            g = _CUBE_256_LOOKUP_16[g]
            b = _CUBE_256_LOOKUP_16[b]
            return _CUBE_START + (r * _CUBE_SIZE_256 + g) * _CUBE_SIZE_256 + b

        # Only remaining possibility is gray value
        if desc.startswith('g#'):
            # hex value 00..ff
            gray = int(desc[2:], 16)
            if gray < 0 or gray > 255:
                return None
            gray = _GRAY_256_LOOKUP[gray]
        elif desc.startswith('g'):
            # decimal value 0..100
            gray = int(desc[1:], 10)
            if gray < 0 or gray > 100:
                return None
            gray = _GRAY_256_LOOKUP_101[gray]
        else:
            return None
        if gray == 0:
            return _CUBE_BLACK
        gray -= 1
        if gray == _GRAY_SIZE_256:
            return _CUBE_WHITE_256
        return _GRAY_START_256 + gray

    except ValueError:
        return None

def _parse_colour_88(desc):
    """
    Return a colour number for the description desc.
    'h0'..'h87' -> 0..87 actual colour number
    '#000'..'#fff' -> 16..79 colour cube colours
    'g0'..'g100' -> 16, 80..87, 79 grays and colour cube black/white
    'g#00'..'g#ff' -> 16, 80...87, 79 gray and colour cube black/white
    
    Returns None if desc is invalid.
    
    >>> _parse_colour_88('h142')
    >>> _parse_colour_88('h42')
    42
    >>> _parse_colour_88('#f00')
    64
    >>> _parse_colour_88('g100')
    79
    >>> _parse_colour_88('g#80')
    83
    """
    if len(desc) > 4:
        # keep the length within reason before parsing
        return None
    try:
        if desc.startswith('h'):
            # high-colour number
            num = int(desc[1:], 10)
            if num < 0 or num > 87:
                return None
            return num

        if desc.startswith('#') and len(desc) == 4:
            # colour-cube coordinates
            rgb = int(desc[1:], 16)
            if rgb < 0:
                return None
            b, rgb = rgb % 16, rgb / 16
            g, r = rgb % 16, rgb / 16
            # find the closest rgb values
            r = _CUBE_88_LOOKUP_16[r]
            g = _CUBE_88_LOOKUP_16[g]
            b = _CUBE_88_LOOKUP_16[b]
            return _CUBE_START + (r * _CUBE_SIZE_88 + g) * _CUBE_SIZE_88 + b

        # Only remaining possibility is gray value
        if desc.startswith('g#'):
            # hex value 00..ff
            gray = int(desc[2:], 16)
            if gray < 0 or gray > 255:
                return None
            gray = _GRAY_88_LOOKUP[gray]
        elif desc.startswith('g'):
            # decimal value 0..100
            gray = int(desc[1:], 10)
            if gray < 0 or gray > 100:
                return None
            gray = _GRAY_88_LOOKUP_101[gray]
        else:
            return None
        if gray == 0:
            return _CUBE_BLACK
        gray -= 1
        if gray == _GRAY_SIZE_88:
            return _CUBE_WHITE_88
        return _GRAY_START_88 + gray

    except ValueError:
        return None

class AttrSpecError(Exception):
    pass

class AttrSpec(object):
    def __init__(self, fg, bg, colours=256):
        """
        fg -- a string containing a comma-separated foreground colour
              and settings

              Colour values:
              'default' (use the terminal's default foreground),
              'black', 'dark red', 'dark green', 'brown', 'dark blue',
              'dark magenta', 'dark cyan', 'light gray', 'dark gray',
              'light red', 'light green', 'yellow', 'light blue', 
              'light magenta', 'light cyan', 'white'

              High-colour example values:
              '#009' (0% red, 0% green, 60% red, like HTML colours)
              '#fcc' (100% red, 80% green, 80% blue)
              'g40' (40% gray, decimal), 'g#cc' (80% gray, hex),
              '#000', 'g0', 'g#00' (black),
              '#fff', 'g100', 'g#ff' (white)
              'h8' (colour number 8), 'h255' (colour number 255)

              Setting:
              'bold', 'underline', 'blink', 'standout'

              Some terminals use 'bold' for bright colours.  Most terminals
              ignore the 'blink' setting.  If the colour is not given then
              'default' will be assumed.

        bg -- a string containing the background colour

              Colour values:
              'default' (use the terminal's default background),
              'black', 'dark red', 'dark green', 'brown', 'dark blue',
              'dark magenta', 'dark cyan', 'light gray'

              High-colour exaples:
              see fg examples above

              An empty string will be treated the same as 'default'.

        colours -- the maximum colours available for the specification

                   Valid values include: 1, 16, 88 and 256.  High-colour 
                   values are only usable with 88 or 256 colours.  With
                   1 colour only the foreground settings may be used.

        >>> AttrSpec('dark red', 'light gray', 16)
        AttrSpec('dark red', 'light gray')
        >>> AttrSpec('yellow, underline, bold', 'dark blue')
        AttrSpec('yellow,bold,underline', 'dark blue')
        >>> AttrSpec('#ddb', '#004', 256) # closest colours will be found
        AttrSpec('#dda', '#006')
        >>> AttrSpec('#ddb', '#004', 88)
        AttrSpec('#ccc', '#000', colours=88)
        """
        if colours not in (1, 16, 88, 256):
            raise AttrSpecError('invalid number of colours (%d).' % colours)
        self._value = 0 | _HIGH_88_COLOUR * (colours == 88)
        self.foreground = fg
        self.background = bg
        if self.colours > colours:
            raise AttrSpecError(('foreground/background (%s/%s) require ' +
                'more colours than have been specified (%d).') %
                (repr(foreground), repr(background), colours))

    def _colours(self):
        """
        Return the maximum colours required for this object.

        Returns 256, 88, 16 or 1.
        """
        if self._value & _HIGH_88_COLOUR:
            return 88
        if self._value & (_BG_HIGH_COLOUR | _FG_HIGH_COLOUR):
            return 256
        if self._value & (_BG_BASIC_COLOUR | _BG_BASIC_COLOUR):
            return 16
        return 1
    colours = property(_colours)

    def __repr__(self):
        """
        Return an executable python representation of the AttrSpec
        object.
        """
        args = "%r, %r" % (self.foreground, self.background)
        if self.colours == 88:
            # 88-colour mode is the only one that is handled differently
            args = args + ", colours=88"
        return "%s(%s)" % (self.__class__.__name__, args)

    def _foreground_colour(self):
        """Return only the colour component of the foreground."""
        if not self._value & (_FG_BASIC_COLOUR | _FG_HIGH_COLOUR):
            return 'default'
        if self._value & _FG_BASIC_COLOUR:
            return _BASIC_COLOURS[self._value & _FG_COLOUR_MASK]
        if self._value & _HIGH_88_COLOUR:
            return _colour_desc_88(self._value & _FG_COLOUR_MASK)
        return _colour_desc_256(self._value & _FG_COLOUR_MASK)

    def _foreground(self):
        colour = self._foreground_colour()
        if self._value & _BOLD:
            colour = colour + ',bold'
        if self._value & _STANDOUT:
            colour = colour + ',standout'
        if self._value & _UNDERLINE:
            colour = colour + ',underline'
        return colour

    def _set_foreground(self, foreground):
        colour = None
        flags = 0
        # handle comma-separated foreground
        for part in foreground.split(','):
            part = part.strip()
            if part in _ATTRIBUTES:
                # parse and store "settings"/attributes in flags
                if flags & _ATTRIBUTES[part]:
                    raise AttrSpecError(("Setting %s specified more than" +
                        "once in foreground (%s)") % (repr(part), 
                        repr(foreground)))
                flags |= _ATTRIBUTES[part]
                continue
            # past this point we must be specifying a colour
            if part == 'default':
                scolour = 0
            elif part in _BASIC_COLOURS:
                scolour = _BASIC_COLOURS.index(part)
                flags |= _FG_BASIC_COLOUR
            elif self._value & _HIGH_88_COLOUR:
                scolour = _parse_colour_88(part)
                flags |= _FG_HIGH_COLOUR
            else:
                scolour = _parse_colour_256(part)
                flags |= _FG_HIGH_COLOUR
            # _parse_colour_*() return None for unrecognised colours
            if scolour is None:
                raise AttrSpecError(("Unrecognised colour specification %s" +
                    "in foreground (%s)") % (repr(part), repr(foreground)))
            if colour is not None:
                raise AttrSpecError(("More than one colour given for " +
                    "foreground (%s)") % (repr(foreground),))
            colour = scolour
        if colour is None:
            raise AttrSpecError("No colour specified for foreground (%s)"
                % (repr(foreground),))
        self._value = (self._value & ~_FG_MASK) | colour | flags

    foreground = property(_foreground, _set_foreground)

    def _background(self):
        """Return the background colour."""
        if not self._value & (_BG_BASIC_COLOUR | _BG_HIGH_COLOUR):
            return 'default'
        if self._value & _BG_BASIC_COLOUR:
            return _BASIC_COLOURS[(self._value & _BG_COLOUR_MASK) >> _BG_SHIFT]
        if self._value & _HIGH_88_COLOUR:
            return _colour_desc_88((self._value & _BG_COLOUR_MASK) >> 
                _BG_SHIFT)
        return _colour_desc_256((self._value & _BG_COLOUR_MASK) >> _BG_SHIFT)
        
    def _set_background(self, background):
        flags = 0
        if background == 'default':
            colour = 0
        elif background in _BASIC_COLOURS:
            colour = _BASIC_COLOURS.index(background)
            flags |= _BG_BASIC_COLOUR
        elif self._value & _HIGH_88_COLOUR:
            colour = _parse_colour_88(background)
            flags |= _BG_HIGH_COLOUR
        else:
            colour = _parse_colour_256(background)
            flags |= _BG_HIGH_COLOUR
        if colour is None:
            raise AttrSpecError(("Unrecognised colour specification " +
                "in background (%s)") % (repr(background),))
        self._value = (self._value & ~_BG_MASK) | (colour << _BG_SHIFT) | flags

    background = property(_background, _set_background)

    def get_rgb_values():
        """
        Return (fg_red, fg_green, fg_blue, bg_red, bg_green, bg_blue) colour
        components.  Each component is in the range 0-255.  Values are taken
        from the XTerm defaults and may not exactly match the user's terminal.
        
        If the foreground or background is 'default' then all their compenents
        will be returned as None.
        """



class RealTerminal(object):
    def __init__(self):
        super(RealTerminal,self).__init__()
        self._signal_keys_set = False
        self._old_signal_keys = None
        
    def tty_signal_keys(self, intr=None, quit=None, start=None, 
        stop=None, susp=None):
        """
        Read and/or set the tty's signal charater settings.
        This function returns the current settings as a tuple.

        Use the string 'undefined' to unmap keys from their signals.
        The value None is used when no change is being made.
        Setting signal keys is done using the integer ascii
        code for the key, eg.  3 for CTRL+C.

        If this function is called after start() has been called
        then the original settings will be restored when stop()
        is called.
        """
        fd = sys.stdin.fileno()
        tattr = termios.tcgetattr(fd)
        sattr = tattr[6]
        skeys = (sattr[termios.VINTR], sattr[termios.VQUIT],
            sattr[termios.VSTART], sattr[termios.VSTOP],
            sattr[termios.VSUSP])
        
        if intr == 'undefined': intr = 0
        if quit == 'undefined': quit = 0
        if start == 'undefined': start = 0
        if stop == 'undefined': stop = 0
        if susp == 'undefined': susp = 0
        
        if intr is not None: tattr[6][termios.VINTR] = intr
        if quit is not None: tattr[6][termios.VQUIT] = quit
        if start is not None: tattr[6][termios.VSTART] = start
        if stop is not None: tattr[6][termios.VSTOP] = stop
        if susp is not None: tattr[6][termios.VSUSP] = susp
        
        if intr is not None or quit is not None or \
            start is not None or stop is not None or \
            susp is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, tattr)
            self._signal_keys_set = True
        
        return skeys
      


def _test():
	import doctest
	doctest.testmod()

if __name__=='__main__':
	_test()
