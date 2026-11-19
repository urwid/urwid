#!/usr/bin/env python

"""Run the browse.py example on a fixed directory to take its documentation screenshots."""

from __future__ import annotations

import os

import real_browse

os.chdir("/usr/share/doc/python3")
real_browse.main()
