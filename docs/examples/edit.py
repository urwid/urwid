#!/usr/bin/env python

import sys
import os
import real_edit

real_edit.EditDisplay(os.path.join(
    os.path.dirname(sys.argv[0]), 'edit_text.txt')).main()
