#!/usr/bin/env python
#
# Urwid setup.py exports the useful bits
#    Copyright (C) 2004  Ian Ward
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

from distutils.core import setup

import os

setup(	name="urwid",
	version=os.popen("make -s release").read().strip(),
	description="urwid -- curses-based UI/widget library",
	author="Ian Ward",
	author_email="ian@excess.org",
	url="http://excess.org/urwid/",
	packages=['urwid'],
     )

