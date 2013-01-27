#!/usr/bin/python
#
# Urwid setup.py exports the useful bits
#    Copyright (C) 2004-2012  Ian Ward
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
    PYTHON3 = not str is bytes
except NameError:
    PYTHON3 = False

try:
    from setuptools import setup, Extension # distribute required for Python 3
    have_setuptools = True
except ImportError:
    if PYTHON3:
        raise
    from distutils.core import setup, Extension
    have_setuptools = False

import os

exec(open(os.path.join("urwid","version.py")).read())
release = __version__

setup_d = {
    'name':"urwid",
    'version':release,
    'author':"Ian Ward",
    'author_email':"ian@excess.org",
    'ext_modules':[Extension('urwid.str_util', sources=['source/str_util.c'])],
    'packages':['urwid'],
    'url':"http://excess.org/urwid/",
    'download_url':"http://excess.org/urwid/urwid-%s.tar.gz"%release,
    'license':"LGPL",
    'keywords':"curses ui widget scroll listbox user interface text layout console ncurses",
    'platforms':"unix-like",
    'description': "A full-featured console (xterm et al.) user interface library",
    'long_description':"""
Urwid is a console user interface library.  It includes many features
useful for text console application developers including:

- Applcations resize quickly and smoothly
- Automatic, programmable text alignment and wrapping
- Simple markup for setting text attributes within blocks of text
- Powerful list box with programmable content for scrolling all widget types
- Your choice of event loops: Twisted, Glib or built-in select-based loop
- Pre-built widgets include edit boxes, buttons, check boxes and radio buttons
- Display modules include raw, curses, and experimental LCD and web displays
- Support for UTF-8, simple 8-bit and CJK encodings
- 256 and 88 color mode support
- Python 3.2 support

Home Page:
  http://excess.org/urwid/

Documentation:
  http://excess.org/urwid/docs/

Example Program Screenshots:
  http://excess.org/urwid/examples.html
"""[1:],
    'classifiers':[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: Console :: Curses",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Widget Sets",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.4",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        ],
     }

if have_setuptools:
    setup_d['zip_safe'] = False
    setup_d['test_suite'] = 'urwid.tests'

if PYTHON3:
    setup_d['use_2to3'] = True

if __name__ == "__main__":
    try:
        setup(**setup_d)
    except (IOError, SystemExit) as e:
        import sys
        if "test" in sys.argv:
            raise
        import traceback
        traceback.print_exc()
        print("Couldn't build the extension module, trying without it...")
        del setup_d["ext_modules"]
        setup(**setup_d)
