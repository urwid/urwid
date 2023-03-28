#!/usr/bin/python
#
# Urwid python compatibility definitions
#    Copyright (C) 2011  Ian Ward
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


# for iterating over byte strings:
# ord2 calls ord in python2 only
# chr2 converts an ordinal value to a length-1 byte string
# B returns a byte string in all supported python versions
# bytes3 creates a byte string from a list of ordinal values

def reraise(tp, value, tb=None):
    """
    Reraise an exception.
    Taken from "six" library (https://pythonhosted.org/six/).
    """
    try:
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
    finally:
        value = None
        tb = None
