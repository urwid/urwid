#!/usr/bin/python
#
# Urwid setup.py exports the useful bits
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

try:
    from setuptools import setup, Extension
        have_setuptools = True
except ImportError:
    from distutils.core import setup, Extension
        have_setuptools = False

import os

import urwid
release = urwid.__version__

setup_d = {
    'name':"urwid",
    'version':release,
    'author':"Ian Ward",
    'author_email':"ian@excess.org",
    'ext_modules':[Extension('urwid.str_util', sources=['source/str_util.c'])],
    'url':"http://excess.org/urwid/",
    'download_url':"http://excess.org/urwid/urwid-%s.tar.gz"%release,
    'license':"LGPL",
    'keywords':"curses ui widget scroll listbox user interface text layout consolt ncurses",
    'platforms':"unix-like",
    'description':(
"A console UI library featuring fluid interface resizing, UTF-8 support,"
" multiple text layouts, simple attribute markup, powerful scrolling list"
" boxes and flexible interface design."),
    'long_description':"""
Urwid is a console user interface library.  It includes many features
useful for text console application developers including:

- Fluid interface resizing (xterm window resizing / fbset on Linux console)
- Support for UTF-8, simple 8-bit and CJK encodings
- 256 and 88 color mode support
- Multiple text alignment and wrapping modes built-in
- Ability to create user-defined text layout classes
- Simple markup for setting text attributes
- Powerful list box that handles scrolling between different widget types
- List box contents may be managed with a user-defined class
- Flexible edit box for editing many different types of text
- Buttons, check boxes and radio buttons
- Customizable layout for all widgets
- Web application display mode using Apache and CGI
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

if have_setuptools:
        setup_d['zip_safe'] = False


try:
    True
except:
    # python 2.1's distutils doesn't understand these:
    del setup_d['classifiers']
    del setup_d['download_url']

if __name__ == "__main__":
    setup( ** setup_d )

