# encoding: utf-8

"""
Example application for integrating serving a Urwid application remotely.

Run this application with::

    twistd -ny twisted_serve_ssh.tac

Then in another terminal run::

    ssh -p 6022 user@localhost

(The password is 'pw' without the quotes.)

Note: To use this in real life, you must use some real checker.
"""

from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse

import urwid
from twisted_serve_ssh import UrwidMind, UrwidUi, create_application


class HelloUi(UrwidUi):
    def create_urwid_toplevel(self):
        txt = urwid.Edit('Hello World?\n ')
        txt2 = urwid.Edit('Hello World?\n ')
        fill = urwid.Filler(urwid.Pile([txt, txt2]), 'top')
        return fill


class HelloMind(UrwidMind):
    ui_factory = HelloUi
    cred_checkers = [InMemoryUsernamePasswordDatabaseDontUse(user='pw')]


application = create_application('TXUrwid Demo', HelloMind, 6022)

# vim: ft=python

