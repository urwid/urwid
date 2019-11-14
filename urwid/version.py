from __future__ import division, print_function

VERSION = (2, 1, 1, 'dev')
__version__ = ''.join(['-.'[type(x) == int]+str(x) for x in VERSION])[1:]
