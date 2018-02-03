#!/usr/bin/env python
#
# Urwid setup.py exports the useful bits
#    Copyright (C) 2004-2014  Ian Ward
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
    'packages':['urwid', 'urwid.tests'],
    'url':"http://urwid.org/",
    'license':"LGPL",
    'keywords':"curses ui widget scroll listbox user interface text layout console ncurses",
    'platforms':"unix-like",
    'description': "A full-featured console (xterm et al.) user interface library",
    'long_description':open("README.rst").read().split('.. content-start\n',1)[1],
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
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: Implementation :: PyPy",
        ],
     }

if have_setuptools:
    setup_d['zip_safe'] = False
    setup_d['test_suite'] = 'urwid.tests'

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
