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

Authors
=======

Creator
-------

`wardi <//github.com/wardi>`_

Maintainers
-----------

`and3rson <//github.com/and3rson>`_,
`tonycpsu <//github.com/tonycpsu>`_,
`ulidtko <//github.com/ulidtko>`_

Contributors
------------

`aathan <//github.com/aathan>`_,
`abadger <//github.com/abadger>`_,
`aglyzov <//github.com/aglyzov>`_,
`akosthekiss <//github.com/akosthekiss>`_,
`alexozer <//github.com/alexozer>`_,
`andersk <//github.com/andersk>`_,
`aszlig <//github.com/aszlig>`_,
`atsampson <//github.com/atsampson>`_,
`BkPHcgQL3V <//github.com/BkPHcgQL3V>`_,
`BlindB0 <//github.com/BlindB0>`_,
`bukzor <//github.com/bukzor>`_,
`eevee <//github.com/eevee>`_,
`federicotdn <//github.com/federicotdn>`_,
`garrison <//github.com/garrison>`_,
`geier <//github.com/geier>`_,
`grugq <//github.com/grugq>`_,
`hkoof <//github.com/hkoof>`_,
`hootnot <//github.com/hootnot>`_,
`horazont <//github.com/horazont>`_,
`inducer <//github.com/inducer>`_,
`ismail-s <//github.com/ismail-s>`_,
`italomaia-bk <//github.com/italomaia-bk>`_,
`ivanov <//github.com/ivanov>`_,
`Julian <//github.com/Julian>`_,
`jwilk <//github.com/jwilk>`_,
`kajojify <//github.com/kajojify>`_,
`Kamik423 <//github.com/Kamik423>`_,
`kkrolczyk <//github.com/kkrolczyk>`_,
`marienz <//github.com/marienz>`_,
`matthijskooijman <//github.com/matthijskooijman>`_,
`mbarkhau <//github.com/mbarkhau>`_,
`mgiusti <//github.com/mgiusti>`_,
`mikemccracken <//github.com/mikemccracken>`_,
`nocarryr <//github.com/nocarryr>`_,
`ntamas <//github.com/ntamas>`_,
`olleolleolle <//github.com/olleolleolle>`_,
`pazz <//github.com/pazz>`_,
`pniedzwiedzinski <//github.com/pniedzwiedzinski>`_,
`raek <//github.com/raek>`_,
`richrd <//github.com/richrd>`_,
`rndusr <//github.com/rndusr>`_,
`robla <//github.com/robla>`_,
`rr- <//github.com/rr->`_,
`seleem1337 <//github.com/seleem1337>`_,
`SenchoPens <//github.com/SenchoPens>`_,
`shyal <//github.com/shyal>`_,
`sitaktif <//github.com/sitaktif>`_,
`tdryer <//github.com/tdryer>`_,
`techtonik <//github.com/techtonik>`_,
`tu500 <//github.com/tu500>`_,
`usrlocalben <//github.com/usrlocalben>`_,
`wackywendell <//github.com/wackywendell>`_,
`wernight <//github.com/wernight>`_,
`westurner <//github.com/westurner>`_,
`whospal <//github.com/whospal>`_,
`Wilfred <//github.com/Wilfred>`_,
`winbornejw <//github.com/winbornejw>`_,
`xnox <//github.com/xnox>`_,
`yanzixiang <//github.com/yanzixiang>`_


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
