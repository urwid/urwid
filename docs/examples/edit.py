#!/usr/bin/env python

"""Run the edit.py example on a fixed file to take its documentation screenshots."""

from __future__ import annotations

import os
import sys

import real_edit

real_edit.EditDisplay(os.path.join(os.path.dirname(sys.argv[0]), "edit_text.txt")).main()
