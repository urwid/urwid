#!/usr/bin/python
#
# Urwid signal dispatching
#    Copyright (C) 2004-2006  Ian Ward
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


class Signals(object):
	def __init__(self):
		self._connections = weakref.WeakKeyDictionary()
		self._supported = {}

	def register(self, sig_cls, signals):
		self._supported[sig_cls] = signals

	def connect(self, obj, name, callback, user_arg=None):
		sig_cls = obj.__class__
		if not name in self._supported.get(sig_cls, []):
			raise NameError, "No such signal %r for object %r" % \
				(name, obj)
		d = self._connections.setdefault(obj, {})
		d.setdefault(name, []).append((callback, user_arg))
		
	def disconnect(self, obj, name, callback, user_arg=None):
		d = self._connections.get(obj, {})
		if name not in d:
			return
		if (callback, user_arg) not in d[name]:
			return
		d[name].remove((callback, user_arg))
 
	def emit(self, obj, name, *args):
		result = False
		d = self._connections.get(obj, {})
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

