#!/usr/bin/python
#
# Urwid signal dispatching
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
        Available as:
        urwid.regsiter_signal(sig_cls, signals)

        sig_class -- the class of an object that will be sending signals
        signals -- a list of signals that may be sent, typically each
            signal is represented by a string

        This function must be called for a class before connecting any
        signal callbacks or emiting any signals from that class' objects
        """
        self._supported[sig_cls] = signals

    def connect(self, obj, name, callback, user_arg=None):
        """
        Available as:
        urwid.connect_signal(obj, name, callback, user_arg=None)

        obj -- the object sending a signal
        name -- the name of the signal, typically a string
        callback -- the function to call when that signal is sent
        user_arg -- optional additional argument to callback, if None
            no arguments will be added
        
        When a matching signal is sent, callback will be called with
        all the positional parameters sent with the signal.  If user_arg
        is not None it will be sent added to the end of the positional
        parameters sent to callback.
        """
        sig_cls = obj.__class__
        if not name in self._supported.get(sig_cls, []):
            raise NameError, "No such signal %r for object %r" % \
                (name, obj)
        d = setdefaultattr(obj, self._signal_attr, {})
        d.setdefault(name, []).append((callback, user_arg))
        
    def disconnect(self, obj, name, callback, user_arg=None):
        """
        Available as:
        urwid.disconnect_signal(obj, name, callback, user_arg=None)

        This function will remove a callback from the list connected
        to a signal with connect_signal().
        """
        d = setdefaultattr(obj, self._signal_attr, {})
        if name not in d:
            return
        if (callback, user_arg) not in d[name]:
            return
        d[name].remove((callback, user_arg))
 
    def emit(self, obj, name, *args):
        """
        Available as:
        urwid.emit_signal(obj, name, *args)

        obj -- the object sending a signal
        name -- the name of the signal, typically a string
        *args -- zero or more positional arguments to pass to the signal
            callback functions

        This function calls each of the callbacks connected to this signal
        with the args arguments as positional parameters.

        This function returns True if any of the callbacks returned True.
        """
        result = False
        d = getattr(obj, self._signal_attr, {})
        for callback, user_arg in d.get(name, []):
            args_copy = args
            if user_arg is not None:
                args_copy = args + (user_arg,)
            result |= bool(callback(*args_copy))
        return result

_signals = Signals()
emit_signal = _signals.emit
register_signal = _signals.register
connect_signal = _signals.connect
disconnect_signal = _signals.disconnect

