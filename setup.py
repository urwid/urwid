#!/usr/bin/env python
#
# Urwid setup.py exports the useful bits
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

from distutils.core import setup

import os

release = "0.9.0-pre2"

setup_d = {
	'name':"urwid",
	'version':release,
	'author':"Ian Ward",
	'author_email':"ian@excess.org",
	'url':"http://excess.org/urwid/",
	'download_url':"http://excess.org/urwid/urwid-%s.tar.gz"%release,
	'license':"LGPL",
	'keywords':"curses ui widget scroll listbox interface text layout",
	'platforms':"unix-like",
	'description':"A curses-based UI library featuring fluid interface resizing, CJK support, multiple text layouts, simple attribute markup, powerful scrolling list boxes and flexible edit boxes.",
	'long_description':"""
Urwid is a curses-based user interface library.  It includes many features
useful for text console application developers including:

- Fluid interface resizing (xterm window resizing / fbset on Linux console)
- Web application display mode using Apache and CGI
- Support for 8-bit and CJK encodings
- Multiple text alignment and wrapping modes built-in
- Ability to register user-defined text alignment and wrapping modes
- Simple markup for setting text attributes
- Powerful list box that handles scrolling between different widget types
- List box contents may be managed with a user-defined class
- Flexible edit box for editing many different types of text
- Buttons, check boxes and radio boxes
- Customizable layout for all widgets
- Easy interface for creating HTML screen shots


Home Page:
  http://excess.org/urwid/

Example Program Screenshots:
  http://excess.org/urwid/examples.html
"""[1:],
	'classifiers':[
		"Development Status :: 4 - Beta",
		"Environment :: Console",
		"Environment :: Console :: Curses",
		"Intended Audience :: Developers",
		"License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
		"Operating System :: POSIX",
		"Operating System :: Unix",
		"Operating System :: MacOS :: MacOS X",
		"Topic :: Software Development :: Libraries :: Python Modules",
		"Topic :: Software Development :: Widget Sets",
		],
	'packages':['urwid'],
     }

try:
	True
except:
	# python 2.1's distutils doesn't understand these:
	del setup_d['classifiers']
	del setup_d['download_url']

setup( ** setup_d )

