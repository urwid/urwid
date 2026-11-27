#!/usr/bin/env python

"""Run the less.py example on its own source to take its documentation screenshots."""

from __future__ import annotations

import os
import sys

import real_less

sys.exit(real_less.main([os.path.join(os.path.dirname(sys.argv[0]), "real_less.py")]))
