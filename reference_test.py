#!/usr/bin/python

import urwid
from weakref import ref

b = urwid.Button("test one")

def hold_b_ref(x):
    print "hello", b

urwid.connect_signal(b, 'click', hold_b_ref)

r = ref(b)

assert r()
del b
# circular reference is detected and removed:
assert not r()

class Foo(object):
    def __init__(self):
        self.btn = urwid.Button("test two")
        urwid.connect_signal(self.btn, 'click', self.say_hi)

    def say_hi(self, btn):
        print "hi"

f = Foo()
r = ref(f.btn)
assert r()
f.btn = None
# circular reference is detected and removed:
assert not r()



b = urwid.Button("test one")
def hold_b_ref(x):
    print "hello", b
urwid.connect_signal(b, 'click', hold_b_ref)
r = ref(b)
assert r()
del hold_b_ref
del b
# circular reference detected and removed:
assert not r()


f = Foo()
r = ref(f)
assert r()
import gc
gc.collect()
f = None
# circular reference only removed after gc.collect()
assert r()
assert gc.collect()
assert not r()
