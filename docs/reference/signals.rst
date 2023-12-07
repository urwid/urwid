Signal Functions
================

.. currentmodule:: urwid

The :func:`urwid.\*_signal` functions use a shared Signals object instance
for tracking registered and connected signals.  There is no reason to
instantiate your own Signals object.

.. function:: connect_signal(obj, name, callback, user_arg=None, weak_args=None, user_args=None)

.. automethod:: Signals.connect

.. function:: disconnect_signal_by_key(obj, name, key)

.. automethod:: Signals.disconnect_by_key

.. function:: disconnect_signal(obj, name, callback, user_arg=None, weak_args=None, user_args=None)

.. automethod:: Signals.disconnect

.. function:: register_signal(sig_cls, signals)

.. automethod:: Signals.register

.. function:: emit_signal(obj, name, \*args)

.. automethod:: Signals.emit
