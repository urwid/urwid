# this is part of the subproc.py example


from __future__ import annotations

import sys

num = int(sys.argv[1])
for c in range(1, 10000000):
    if num % c == 0:
        print("factor:", c)
