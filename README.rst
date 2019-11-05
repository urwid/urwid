Urwid
=====
|pypi| |docs| |travis| |coveralls|

.. content-start

About
=====

Urwid is a console user interface library for Python.
It includes many features useful for text console application developers including:

- Applications resize quickly and smoothly
- Automatic, programmable text alignment and wrapping
- Simple markup for setting text attributes within blocks of text
- Powerful list box with programmable content for scrolling all widget types
- Your choice of event loops: Twisted, Glib, Tornado or select-based loop
- Pre-built widgets include edit boxes, buttons, check boxes and radio buttons
- Display modules include raw, curses, and experimental LCD and web displays
- Support for UTF-8, simple 8-bit and CJK encodings
- 24-bit (true color), 256 color, and 88 color mode support
- Compatible with Python 2.7, 3.4+ and PyPy

Home Page:
  http://urwid.org/

Installation
============

To install using pip

.. code:: bash
   
   pip install urwid

Alternatively if you are on Debian or Ubuntu

.. code:: bash

   apt-get install python-urwid

Testing
=======

To run tests locally, install & run `tox`. You must have
appropriate Python versions installed to run `tox` for
each of them.

To test code in all Python versions:

.. code:: bash

    tox                    # Test all versions specified in tox.ini:
    tox -e py36            # Test Python 3.6 only
    tox -e py27,py36,pypy  # Test Python 2.7, Python 3.6 & pypy

Supported Python versions
=========================

- 2.7
- 3.4
- 3.5
- 3.6
- 3.7
- 3.8
- pypy

Contributors
============

- `wardi <//github.com/wardi>`_
- `aszlig <//github.com/aszlig>`_
- `mgiusti <//github.com/mgiusti>`_
- `and3rson <//github.com/and3rson>`_
- `pazz <//github.com/pazz>`_
- `wackywendell <//github.com/wackywendell>`_
- `eevee <//github.com/eevee>`_
- `marienz <//github.com/marienz>`_
- `rndusr <//github.com/rndusr>`_
- `matthijskooijman <//github.com/matthijskooijman>`_
- `Julian <//github.com/Julian>`_
- `techtonik <//github.com/techtonik>`_
- `garrison <//github.com/garrison>`_
- `ivanov <//github.com/ivanov>`_
- `abadger <//github.com/abadger>`_
- `aglyzov <//github.com/aglyzov>`_
- `ismail-s <//github.com/ismail-s>`_
- `horazont <//github.com/horazont>`_
- `robla <//github.com/robla>`_
- `usrlocalben <//github.com/usrlocalben>`_
- `geier <//github.com/geier>`_
- `federicotdn <//github.com/federicotdn>`_
- `jwilk <//github.com/jwilk>`_
- `rr- <//github.com/rr->`_
- `tonycpsu <//github.com/tonycpsu>`_
- `westurner <//github.com/westurner>`_
- `grugq <//github.com/grugq>`_
- `inducer <//github.com/inducer>`_
- `winbornejw <//github.com/winbornejw>`_
- `hootnot <//github.com/hootnot>`_
- `raek <//github.com/raek>`_


.. |pypi| image:: http://img.shields.io/pypi/v/urwid.svg
    :alt: current version on PyPi
    :target: https://pypi.python.org/pypi/urwid

.. |docs| image:: https://readthedocs.org/projects/urwid/badge/
    :alt: docs link
    :target: http://urwid.readthedocs.org/en/latest/

.. |travis| image:: https://travis-ci.org/urwid/urwid.svg?branch=master
    :alt: build status
    :target: https://travis-ci.org/urwid/urwid/

.. |coveralls| image:: https://coveralls.io/repos/github/urwid/urwid/badge.svg
    :alt: test coverage
    :target: https://coveralls.io/github/urwid/urwid
