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
    This class can trigger a callback any time its contents are changed
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
        >>> ml
        MonitoredList([1, 2, 3])
        >>> ml.append(10)
        modified
        >>> len(ml)
        4
        >>> ml += [11, 12, 13]
        modified
        >>> ml[:] = ml[:2] + ml[-2:]
        modified
        >>> ml
        MonitoredList([1, 2, 12, 13])
        """
        self._modified = callback

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, list(self))

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


class MonitoredFocusList(MonitoredList):
    """
    This class can trigger a callback any time its contents are changed
    and any time the item "in focus" is modified or removed
    """
    def __init__(self, *argl, **argd):
        """
        This is a list that tracks one item as the focus item.  If items
        are inserted or removed it will update the focus.

        >>> ml = MonitoredFocusList([10, 11, 12, 13, 14], focus=3)
        >>> ml
        MonitoredFocusList([10, 11, 12, 13, 14], focus=3)
        >>> del(ml[1])
        >>> ml
        MonitoredFocusList([10, 12, 13, 14], focus=2)
        >>> ml[:2] = [50, 51, 52, 53]
        >>> ml
        MonitoredFocusList([50, 51, 52, 53, 13, 14], focus=4)
        >>> ml[4] = 99
        >>> ml
        MonitoredFocusList([50, 51, 52, 53, 99, 14], focus=4)
        >>> ml[:] = []
        >>> ml
        MonitoredFocusList([], focus=None)
        """
        focus = 0
        if 'focus' in argd:
            focus = argd['focus']
            del argd['focus']

        super(MonitoredFocusList, self).__init__(*argl, **argd)

        self.set_focus(focus)
        self._focus_modified = lambda ml, indices, new_items: None

    def __repr__(self):
        return "%s(%r, focus=%r)" % (
            self.__class__.__name__, list(self), self.get_focus())

    def get_focus(self):
        """
        Return the index of the item "in focus" or None if
        the list is empty.  May also be accessed as .focus

        >>> MonitoredFocusList([1,2,3], focus=2).get_focus()
        2
        >>> MonitoredFocusList().get_focus()
        >>> MonitoredFocusList([1,2,3], focus=1).focus
        1
        """
        if not self:
            return None
        if self._focus >= len(self):
            # should't happen.. but just in case
            return len(self)-1
        return self._focus

    def set_focus(self, index):
        """
        index -- index into self.widget_list, negative indexes count from
            the end, any index out of range will raise an IndexError
        
        Negative indexes work the same way they do in slicing.

        May also be set using .focus
        
        >>> ml = MonitoredFocusList([9, 10, 11])
        >>> ml.set_focus(2); ml.get_focus()
        2
        >>> ml.set_focus(-2); ml.get_focus()
        1
        >>> ml.focus = 0; ml.get_focus()
        0
        """
        if not self:
            self._focus = 0
            return
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError('list index out of range')
        self._focus = int(index)

    focus = property(get_focus, set_focus)

    def set_focus_modified_callback(self, callback):
        """
        Assign a function to handle updating the focus when the item
        in focus is about to be changed.  The callback is in the form:

        callback(monitored_list, slc, new_items)
        indices -- a (start, stop, step) tuple whose range covers the 
            items being modified
        new_items -- a list of items replacing those at range(*indices)
        
        The only valid action for the callback is to call set_focus().
        Modifying the list in the callback has undefined behaviour.
        """
        self._focus_modified = callback

    def _handle_possible_focus_modified(self, slc, new_items=[]):
        """
        Default behaviour is to move the focus to the item following
        any removed items, or the last item in the list if that doesn't
        exist.
        """
        num_new_items = len(new_items)
        start, stop, step = indices = slc.indices(len(self))
        if step == 1:
            if start <= self._focus < stop:
                # call user handler, which might modify focus
                self._focus_modified(self, indices, new_items)

            if start + num_new_items <= self._focus < stop:
                self._focus = stop
            # adjust for added/removed items
            if stop <= self._focus:
                self._focus += num_new_items - (stop - start)

        else:
            removed = range(start, stop, step)
            if self._focus in removed:
                # call user handler, which might modify focus
                self._focus_modified(self, indices, new_items)

            if not num_new_items:
                # extended slice being removed
                if self._focus in removed:
                    self._focus += 1

                # adjust for removed items
                self._focus -= len(range(start, self._focus, step))

    def _clamp_focus(self):
        """
        adjust the focus if it is out of range
        """
        if self._focus >= len(self):
            self._focus = len(self)-1
        if self._focus < 0:
            self._focus = 0

    # override all the list methods that might affect our focus
    
    def __delitem__(self, y):
        """
        >>> ml = MonitoredFocusList([0,1,2,3], focus=2)
        >>> del ml[3]; ml
        MonitoredFocusList([0, 1, 2], focus=2)
        >>> del ml[0]; ml
        MonitoredFocusList([1, 2], focus=1)
        >>> del ml[1]; ml
        MonitoredFocusList([1], focus=0)
        >>> del ml[0]; ml
        MonitoredFocusList([], focus=None)
        >>> ml = MonitoredFocusList([5,4,6,4,5,4,6,4,5], focus=4)
        >>> del ml[1::2]; ml
        MonitoredFocusList([5, 6, 5, 6, 5], focus=2)
        >>> del ml[::2]; ml
        MonitoredFocusList([6, 6], focus=1)
        """
        if isinstance(y, slice):
            self._handle_possible_focus_modified(y)
        else:
            self._handle_possible_focus_modified(slice(y, y+1))
        rval = super(MonitoredFocusList, self).__delitem__(y)
        self._clamp_focus()
        return rval

    def __setitem__(self, i, y):
        """
        >>> def modified(monitored_list, indices, new_items):
        ...     print "range%r <- %r" % (indices, new_items)
        >>> ml = MonitoredFocusList([0,1,2,3], focus=2)
        >>> ml.set_focus_modified_callback(modified)
        >>> ml[0] = 9
        >>> ml[2] = 6
        range(2, 3, 1) <- [6]
        >>> ml[-1] = 8; ml
        MonitoredFocusList([9, 1, 6, 8], focus=2)
        >>> ml[1::2] = [12, 13]
        >>> ml[::2] = [10, 11]
        range(0, 4, 2) <- [10, 11]
        """
        if isinstance(i, slice):
            self._handle_possible_focus_modified(i, y)
        else:
            self._handle_possible_focus_modified(slice(i, i+1 or None), [y])
        return super(MonitoredFocusList, self).__setitem__(i, y)

    def __delslice__(self, i, j):
        """
        >>> def modified(monitored_list, indices, new_items):
        ...     print "range%r <- %r" % (indices, new_items)
        >>> ml = MonitoredFocusList([0,1,2,3,4], focus=2)
        >>> ml.set_focus_modified_callback(modified)
        >>> del ml[3:5]; ml
        MonitoredFocusList([0, 1, 2], focus=2)
        >>> del ml[:1]; ml
        MonitoredFocusList([1, 2], focus=1)
        >>> del ml[1:]; ml
        range(1, 2, 1) <- []
        MonitoredFocusList([1], focus=0)
        >>> del ml[:]; ml
        range(0, 1, 1) <- []
        MonitoredFocusList([], focus=None)
        """
        self._handle_possible_focus_modified(slice(i, j))
        rval = super(MonitoredFocusList, self).__delslice__(i, j)
        self._clamp_focus()
        return rval

    def __setslice__(self, i, j, y):
        """
        >>> ml = MonitoredFocusList([0,1,2,3,4], focus=2)
        >>> ml[3:5] = [-1]; ml
        MonitoredFocusList([0, 1, 2, -1], focus=2)
        >>> ml[0:1] = []; ml
        MonitoredFocusList([1, 2, -1], focus=1)
        >>> ml[1:] = [3, 4]; ml
        MonitoredFocusList([1, 3, 4], focus=1)
        >>> ml[1:] = [2]; ml
        MonitoredFocusList([1, 2], focus=1)
        >>> ml[0:1] = [9,9,9]; ml
        MonitoredFocusList([9, 9, 9, 2], focus=3)
        >>> ml[:] = []; ml
        MonitoredFocusList([], focus=None)
        """
        self._handle_possible_focus_modified(slice(i, j), y)
        rval = super(MonitoredFocusList, self).__setslice__(i, j, y)
        self._clamp_focus()
        return rval
    
    def insert(self, index, object):
        """
        >>> ml = MonitoredFocusList([0,1,2,3], focus=2)
        >>> ml.insert(-1, -1); ml
        MonitoredFocusList([0, 1, 2, -1, 3], focus=2)
        >>> ml.insert(0, -2); ml
        MonitoredFocusList([-2, 0, 1, 2, -1, 3], focus=3)
        >>> ml.insert(3, -3); ml
        MonitoredFocusList([-2, 0, 1, -3, 2, -1, 3], focus=4)
        """
        self._handle_possible_focus_modified(slice(index, index), [object])
        return super(MonitoredFocusList, self).insert(index, object)

    def pop(self, index=-1):
        """
        >>> ml = MonitoredFocusList([-2,0,1,-3,2,3], focus=4)
        >>> ml.pop(3); ml
        -3
        MonitoredFocusList([-2, 0, 1, 2, 3], focus=3)
        >>> ml.pop(0); ml
        -2
        MonitoredFocusList([0, 1, 2, 3], focus=2)
        >>> ml.pop(-1); ml
        3
        MonitoredFocusList([0, 1, 2], focus=2)
        >>> ml.pop(2); ml
        2
        MonitoredFocusList([0, 1], focus=1)
        """
        self._handle_possible_focus_modified(slice(index, index+1 or None))
        return super(MonitoredFocusList, self).pop(index)

    def remove(self, value):
        """
        >>> ml = MonitoredFocusList([-2,0,1,-3,2,-1,3], focus=4)
        >>> ml.remove(-3); ml
        MonitoredFocusList([-2, 0, 1, 2, -1, 3], focus=3)
        >>> ml.remove(-2); ml
        MonitoredFocusList([0, 1, 2, -1, 3], focus=2)
        >>> ml.remove(3); ml
        MonitoredFocusList([0, 1, 2, -1], focus=2)
        """
        index = self.index(value)
        self._handle_possible_focus_modified(slice(index, index+1 or None))
        return super(MonitoredFocusList, self).remove(value)

    def reverse(self):
        """
        >>> ml = MonitoredFocusList([0,1,2,3,4], focus=1)
        >>> ml.reverse(); ml
        MonitoredFocusList([4, 3, 2, 1, 0], focus=3)
        """
        self._focus = max(0, len(self) - self._focus - 1)
        return super(MonitoredFocusList, self).reverse()

    def sort(self):
        """
        >>> ml = MonitoredFocusList([-2,0,1,-3,2,-1,3], focus=4)
        >>> ml.sort(); ml
        MonitoredFocusList([-3, -2, -1, 0, 1, 2, 3], focus=5)
        """
        if not self:
            return
        value = self[self._focus]
        rval = super(MonitoredFocusList, self).sort()
        self._focus = self.index(value)
        return rval





def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

