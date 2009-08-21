#!/usr/bin/python
#
# Urwid MonitoredList class
#    Copyright (C) 2004-2009  Ian Ward
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



def _call_modified(fn):
    def call_modified_wrapper(self, *args, **kwargs):
        rval = fn(self, *args, **kwargs)
        self._modified()
        return rval
    return call_modified_wrapper

class MonitoredList(list):
    """
    This class triggers a callback any time its contents are changed
    with the usual list operations append, extend, etc.
    """
    def _modified(self):
        pass
    
    def set_modified_callback(self, callback):
        """
        Assign a callback function in with no parameters.
        Callback's return value is ignored.

        >>> import sys
        >>> ml = MonitoredList([1,2,3])
        >>> ml.set_modified_callback(lambda: sys.stdout.write("modified\\n"))
        >>> list(ml)
        [1, 2, 3]
        >>> ml.append(10)
        modified
        >>> len(ml)
        4
        >>> ml += [11, 12, 13]; ml[:] = ml[:2] + ml[-2:]
        modified
        modified
        >>> list(ml)
        [1, 2, 12, 13]
        """
        self._modified = callback

    def __repr__(self):
        return "%s.%s(%s)" % (self.__class__.__module__,
            self.__class__.__name__,
            list.__repr__(self))

    __add__ = _call_modified(list.__add__)
    __delitem__ = _call_modified(list.__delitem__)
    __delslice__ = _call_modified(list.__delslice__)
    __iadd__ = _call_modified(list.__iadd__)
    __imul__ = _call_modified(list.__imul__)
    __rmul__ = _call_modified(list.__rmul__)
    __setitem__ = _call_modified(list.__setitem__)
    __setslice__ = _call_modified(list.__setslice__)
    append = _call_modified(list.append)
    extend = _call_modified(list.extend)
    insert = _call_modified(list.insert)
    pop = _call_modified(list.pop)
    remove = _call_modified(list.remove)
    reverse = _call_modified(list.reverse)
    sort = _call_modified(list.sort)



def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

