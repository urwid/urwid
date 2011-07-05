# this is part of the subproc.py example

import sys

num = int(sys.argv[1])
for c in xrange(1,10000000):
    if num % c == 0:
        print "factor:", c
