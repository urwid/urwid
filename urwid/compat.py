#!/usr/bin/python
# -*- coding: utf-8 -*-
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

from __future__ import division, print_function

import sys

try: # python 2.4 and 2.5 compat
    bytes = bytes
except NameError:
    bytes = str

PYTHON3 = sys.version_info > (3, 0)

# for iterating over byte strings:
# ord2 calls ord in python2 only
# chr2 converts an ordinal value to a length-1 byte string
# B returns a byte string in all supported python versions
# bytes3 creates a byte string from a list of ordinal values
if PYTHON3:
    ord2 = lambda x: x
    chr2 = lambda x: bytes([x])
    B = lambda x: x.encode('iso8859-1')
    bytes3 = bytes
    text_type = str
    xrange = range
    text_types = (str,)
else:
    ord2 = ord
    chr2 = chr
    B = lambda x: x
    bytes3 = lambda x: bytes().join([chr(c) for c in x])
    text_type = unicode
    xrange = xrange
    text_types = (str, unicode)


def with_metaclass(meta, *bases):
    """
    Create a base class with a metaclass.
    Taken from "six" library (https://pythonhosted.org/six/).
    """
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    class metaclass(type):

        def __new__(cls, name, this_bases, d):
            return meta(name, bases, d)

        @classmethod
        def __prepare__(cls, name, this_bases):
            return meta.__prepare__(name, bases)
    return type.__new__(metaclass, 'temporary_class', (), {})

