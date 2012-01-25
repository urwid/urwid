#!/usr/bin/python
#
# Urwid signal dispatching
#    Copyright (C) 2004-2012  Ian Ward
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


import itertools
import weakref


class MetaSignals(type):
    """
    register the list of signals in the class varable signals,
    including signals in superclasses.
    """
    def __init__(cls, name, bases, d):
        signals = d.get("signals", [])
        for superclass in cls.__bases__:
            signals.extend(getattr(superclass, 'signals', []))
        signals = dict([(x,None) for x in signals]).keys()
        d["signals"] = signals
        register_signal(cls, signals)
        super(MetaSignals, cls).__init__(name, bases, d)

def setdefaultattr(obj, name, value):
    # like dict.setdefault() for object attributes
    if hasattr(obj, name):
        return getattr(obj, name)
    setattr(obj, name, value)
    return value

class Signals(object):
    _signal_attr = '_urwid_signals' # attribute to attach to signal senders

    def __init__(self):
        self._supported = {}

    def register(self, sig_cls, signals):
        """
        :param sig_class: the class of an object that will be sending signals
        :type sig_class: class
        :param signals: a list of signals that may be sent, typically each
                        signal is represented by a string
        :type signals: signal names

        This function must be called for a class before connecting any
        signal callbacks or emiting any signals from that class' objects
        """
        self._supported[sig_cls] = signals

    def connect(self, obj, name, callback, user_arg=None, weak_args=[], user_args=[]):
        """
        :param obj: the object sending a signal
        :type obj: object
        :param name: the signal to listen for, typically a string
        :type name: signal name
        :param callback: the function to call when that signal is sent
        :type callback: function
        :param user_arg: deprecated additional argument to callback (appended
                         after the arguments passed when the signal is
                         emitted). If None no arguments will be added.
                         Don't use this argument, use user_args instead.
        :param weak_args: additional arguments passed to the callback
                          (before any arguments passed when the signal
                          is emitted and before any user_args).

                          These arguments are stored as weak references
                          (but converted back into their original value
                          before passing them to callback) to prevent
                          any objects referenced (indirectly) from
                          weak_args from being kept alive just because
                          they are referenced by this signal handler.

                          Use this argument only as a keyword argument,
                          since user_arg might be removed in the future.
        :type weak_args: iterable
        :param user_args: additional arguments to pass to the callback,
                          (before any arguments passed when the signal
                          is emitted but after any weak_args).

                          Use this argument only as a keyword argument,
                          since user_arg might be removed in the future.
        :type user_args: iterable

        When a matching signal is sent, callback will be called. The
        arguments it receives will be the user_args passed at connect
        time (as individual arguments) followed by all the positional
        parameters sent with the signal.

        As an example of using weak_args, consider the following snippet:

        debug = urwid.Text('')
        def print_debug(widget, newtext):
            debug.set_text("Edit widget changed to %s" % newtext)

        edit = urwid.Edit('')
        urwid.connect_signal(edit, 'change', handler)

        If you now build some interface using "edit" and "debug", the
        "debug" widget will show whatever you type in the "edit" widget.
        However, if you remove all references to the "debug" widget, it
        will still be kept alive by the signal handler. This because the
        signal handler is a closure that (implicitly) references the
        "edit" widget. If you want to allow the "debug" widget to be
        garbage collected, you can create a "fake" or "weak" closure
        (it's not really a closure, since it doesn't reference any
        outside variables, so it's just a dynamic function):

        debug = urwid.Text('')
        def print_debug(weak_debug, widget, newtext):
            weak_debug.set_text("Edit widget changed to %s" % newtext)

        edit = urwid.Edit('')
        urwid.connect_signal(edit, 'change', handler, weak_args=[debug])

        Here the weak_debug parameter in print_debug is the value passed
        in the weak_args list to connect_signal. Note that the
        weak_debug value passed is not a weak reference anymore, the
        signals code transparently dereferences the weakref parameter
        before passing it to print_debug.
        """

        sig_cls = obj.__class__
        if not name in self._supported.get(sig_cls, []):
            raise NameError, "No such signal %r for object %r" % \
                (name, obj)

        user_args = self._prepare_user_args(weak_args, user_args)

        d = setdefaultattr(obj, self._signal_attr, {})
        d.setdefault(name, []).append((callback, user_arg, user_args))

    def _prepare_user_args(self, weak_args, user_args):
        # Turn weak_args into weakrefs and prepend them to user_args
        return [weakref.ref(a) for a in weak_args] + user_args


    def disconnect(self, obj, name, callback, user_arg=None, weak_args=[], user_args=[]):
        """
        This function will remove a callback from the list connected
        to a signal with connect_signal().
        """
        d = setdefaultattr(obj, self._signal_attr, {})
        if name not in d:
            return

        # Do the same processing as in connect, so we can compare the
        # resulting tuple.
        user_args = self._prepare_user_args(weak_args, user_args)

        if (callback, user_arg, user_args) not in d[name]:
            return

        d[name].remove((callback, user_arg, user_args))

    def emit(self, obj, name, *args):
        """
        :param obj: the object sending a signal
        :type obj: object
        :param name: the signal to send, typically a string
        :type name: signal name
        :param \*args: zero or more positional arguments to pass to the signal
                      callback functions

        This function calls each of the callbacks connected to this signal
        with the args arguments as positional parameters.

        This function returns True if any of the callbacks returned True.
        """
        result = False
        d = getattr(obj, self._signal_attr, {})
        for callback, user_arg, user_args in d.get(name, []):
            result |= self._call_callback(callback, user_arg, user_args, args)
        return result

    def _call_callback(self, callback, user_arg, user_args, emit_args):
        if user_args:
            args_to_pass = []
            for arg in user_args:
                if isinstance(arg, weakref.ReferenceType):
                    arg = arg()
                    if arg is None:
                        # If the weakref is None, the referenced
                        # object was cleaned up. We just skip the
                        # entire callback in this case.
                        # TODO: remove the callback from the list
                        # when this happens
                        return False
                args_to_pass.append(arg)

            args_to_pass.extend(emit_args)
        else:
            # Optimization: Don't create a new list when there are
            # no user_args
            args_to_pass = emit_args

        # The deprecated user_arg argument was added to the end
        # instead of the beginning.
        if user_arg is not None:
            args_to_pass = itertools.chain(args_to_pass, (user_arg,))

        return bool(callback(*args_to_pass))

_signals = Signals()
emit_signal = _signals.emit
register_signal = _signals.register
connect_signal = _signals.connect
disconnect_signal = _signals.disconnect

