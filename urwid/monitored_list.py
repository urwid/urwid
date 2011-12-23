#!/usr/bin/python
#
# Urwid MonitoredList class
#    Copyright (C) 2004-2011  Ian Ward
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


from urwid.compat import PYTHON3


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
        Assign a callback function with no parameters that is called any
        time the list is modified.  Callback's return value is ignored.

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
    if not PYTHON3:
        __delslice__ = _call_modified(list.__delslice__)
    __iadd__ = _call_modified(list.__iadd__)
    __imul__ = _call_modified(list.__imul__)
    __rmul__ = _call_modified(list.__rmul__)
    __setitem__ = _call_modified(list.__setitem__)
    if not PYTHON3:
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
        focus = argd.pop('focus', 0)

        super(MonitoredFocusList, self).__init__(*argl, **argd)

        self._focus = focus
        self._focus_modified = lambda ml, indices, new_items: None

    def __repr__(self):
        return "%s(%r, focus=%r)" % (
            self.__class__.__name__, list(self), self.focus)

    def _get_focus(self):
        """
        Return the index of the item "in focus" or None if
        the list is empty.

        >>> MonitoredFocusList([1,2,3], focus=2)._get_focus()
        2
        >>> MonitoredFocusList()._get_focus()
        """
        if not self:
            return None
        return self._focus

    def _set_focus(self, index):
        """
        index -- index into this list, any index out of range will
            raise an IndexError

        This function may call self._focus_changed when the focus
        is actually modified.  That method may be 

        >>> ml = MonitoredFocusList([9, 10, 11])
        >>> ml._set_focus(2); ml._get_focus()
        2
        >>> ml._set_focus(0); ml._get_focus()
        0
        >>> ml._set_focus(-2)
        Traceback (most recent call last):
        ...
        IndexError: focus index is out of range: -2
        """
        if not self:
            self._focus = 0
            return
        if index < 0 or index >= len(self):
            raise IndexError, 'focus index is out of range: %s' % (index,)
        if index != int(index):
            raise IndexError, 'invalid focus index: %s' % (index,)
        index = int(index)
        if index != self._focus:
            self._focus_changed(index)
        self._focus = index

    focus = property(_get_focus, _set_focus, doc="""
        Get/set the focus index.  This value is read as None when the list
        is empty, and may only be set to a value between 0 and len(self)-1
        or an IndexError will be raised.
        """)

    def _focus_changed(self, new_focus):
        pass

    def set_focus_changed_callback(self, callback):
        """
        Assign a callback to be called when the focus index changes
        for any reason.  The callback is in the form:

        callback(new_focus)
        new_focus -- new focus index

        >>> import sys
        >>> ml = MonitoredFocusList([1,2,3], focus=1)
        >>> ml.set_focus_changed_callback(lambda f: sys.stdout.write("focus: %d\\n" % (f,)))
        >>> ml
        MonitoredFocusList([1, 2, 3], focus=1)
        >>> ml.append(10)
        >>> ml.insert(1, 11)
        focus: 2
        >>> ml
        MonitoredFocusList([1, 11, 2, 3, 10], focus=2)
        >>> del ml[:2]
        focus: 0
        >>> ml[:0] = [12, 13, 14]
        focus: 3
        >>> ml.focus = 5
        focus: 5
        >>> ml
        MonitoredFocusList([12, 13, 14, 2, 3, 10], focus=5)
        """
        self._focus_changed = callback

    def _focus_removed(self, indices, new_items):
        return None

    def set_focus_removed_callback(self, callback):
        """
        Assign a function to handle updating the focus when the item
        in focus is about to be removed or replaced with something
        else.  The callback is in the form:

        callback(indices, new_items)
        indices -- a (start, stop, step) tuple whose range covers the
            items being modified
        new_items -- a list of items replacing those at range(*indices),
            empty if items are being removed

        The callback may return an integer position to be the new
        focus after the list is modified, or None to use the default
        behaviour.
        """
        self._focus_removed = callback

    def _handle_possible_focus_removed(self, slc, new_items=[]):
        """
        Default behaviour is to move the focus to the item following
        any removed items, or the last item in the list if that doesn't
        exist.

        returns focus position for after change is applied
        """
        num_new_items = len(new_items)
        start, stop, step = indices = slc.indices(len(self))
        num_removed = len(range(*indices))
        focus = self._focus
        if step == 1:
            if start <= focus < stop:
                new_focus = self._focus_removed(indices, new_items)
                if new_focus is not None:
                    focus = new_focus

            if start + num_new_items <= focus < stop:
                focus = stop
            # adjust for added/removed items
            if stop <= focus:
                focus += num_new_items - (stop - start)

        else:
            removed = range(start, stop, step)
            if focus in removed:
                new_focus = self._focus_removed(indices, new_items)
                if new_focus is not None:
                    focus = new_focus

            if not num_new_items:
                # extended slice being removed
                if focus in removed:
                    focus += 1

                # adjust for removed items
                focus -= len(range(start, min(focus, stop), step))

        return min(focus, len(self) + num_new_items - num_removed -1)

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
            focus = self._handle_possible_focus_removed(y)
        else:
            focus = self._handle_possible_focus_removed(slice(y, y+1))
        rval = super(MonitoredFocusList, self).__delitem__(y)
        self._set_focus(focus)
        return rval

    def __setitem__(self, i, y):
        """
        >>> def modified(indices, new_items):
        ...     print "range%r <- %r" % (indices, new_items)
        >>> ml = MonitoredFocusList([0,1,2,3], focus=2)
        >>> ml.set_focus_removed_callback(modified)
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
            focus = self._handle_possible_focus_removed(i, y)
        else:
            focus = self._handle_possible_focus_removed(slice(i, i+1 or None), [y])
        rval = super(MonitoredFocusList, self).__setitem__(i, y)
        self._set_focus(focus)
        return rval

    def __delslice__(self, i, j):
        """
        >>> def modified(indices, new_items):
        ...     print "range%r <- %r" % (indices, new_items)
        >>> ml = MonitoredFocusList([0,1,2,3,4], focus=2)
        >>> ml.set_focus_removed_callback(modified)
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
        focus = self._handle_possible_focus_removed(slice(i, j))
        rval = super(MonitoredFocusList, self).__delslice__(i, j)
        self._set_focus(focus)
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
        focus = self._handle_possible_focus_removed(slice(i, j), y)
        rval = super(MonitoredFocusList, self).__setslice__(i, j, y)
        self._set_focus(focus)
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
        focus = self._handle_possible_focus_removed(slice(index, index),
            [object])
        rval = super(MonitoredFocusList, self).insert(index, object)
        self._set_focus(focus)
        return rval

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
        focus = self._handle_possible_focus_removed(slice(index,
            index+1 or None))
        rval = super(MonitoredFocusList, self).pop(index)
        self._set_focus(focus)
        return rval

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
        focus = self._handle_possible_focus_removed(slice(index,
            index+1 or None))
        rval = super(MonitoredFocusList, self).remove(value)
        self._set_focus(focus)
        return rval

    def reverse(self):
        """
        >>> ml = MonitoredFocusList([0,1,2,3,4], focus=1)
        >>> ml.reverse(); ml
        MonitoredFocusList([4, 3, 2, 1, 0], focus=3)
        """
        rval = super(MonitoredFocusList, self).reverse()
        self._set_focus(max(0, len(self) - self._focus - 1))
        return rval

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
        self._set_focus(self.index(value))
        return rval





def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

