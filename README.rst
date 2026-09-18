Urwid
=====
|pypi| |docs| |gitter| |ci| |pre-commit| |coveralls|

About
=====

Urwid is a console user interface library for Python on Linux, OSX, Cygwin or other unix-like OS
and partially supports Windows OS (see below).

It includes many features useful for text console application developers including:

- Applications resize quickly and smoothly
- Automatic, programmable text alignment and wrapping
- Simple markup for setting text attributes within blocks of text
- Powerful list box with programmable content for scrolling all widget types
- Your choice of event loops: Twisted, Glib, Tornado, asyncio, trio, ZeroMQ or select-based loop
- Pre-built widgets include edit boxes, buttons, check boxes and radio buttons
- Display modules include raw, curses, and experimental LCD and web displays
- Support for UTF-8, simple 8-bit and CJK encodings
- 24-bit (true color), 256 color, and 88 color mode support
- Compatible with Python 3.9+ and PyPy

Home Page:
  http://urwid.org/

Installation
============

To install using pip

.. code:: bash

   pip install urwid

For advanced functionality extra requirements need to be installed.
Example for ZeroMQ event loop and LCD display:

.. code:: bash

    pip install urwid[serial,zmq]

Alternatively if you are on Debian or Ubuntu

.. code:: bash

   apt-get install python3-urwid

Windows support notes
=====================

Windows support is limited to the Windows 10+ due to ANSI support requirement.

* Not supported:

1. Terminal widget and all related render API (TermCanvas, TermCharset, TermModes, TermScroller)
2. Any file descriptors except sockets (Windows OS limitation)
3. ZMQEventLoop.

* Special requirements:

1. Extra libraries required for curses display support:

.. code-block:: bash

    pip install urwid[curses]

* CursesDisplay incorrectly handles mouse input in case of fast actions.
* Only UTF-8 mode is supported.


Testing
=======

To run tests locally, install & run `tox`. You must have
appropriate Python versions installed to run `tox` for each of them.

To test code in all Python versions:

.. code:: bash

    tox                           # Test all versions specified in tox.ini
    tox -e py39                   # Test Python 3.9 only
    tox -e py313t                 # Test Python 3.13 with free-threading
    tox -e pypy3                  # Test PyPy3
    tox -e py39,py310,pypy3       # Test specific versions

Testing different Python implementations
----------------------------------------

**CPython standard (default)**

Tests all optional extras including C extensions (glib, zmq, twisted).

.. code:: bash

    tox -e py313

**Free-threaded CPython (3.13+)**

Tests with compatible extras (tornado, trio, twisted, serial). Excludes C extensions without free-threading wheel support.

.. code:: bash

    tox -e py313t        # Python 3.13 free-threaded (PEP 703)
    tox -e py314t        # Python 3.14 free-threaded
    tox -e py315t        # Python 3.15 free-threaded

**PyPy3**

Tests with compatible extras (tornado, trio, serial). Excludes problematic C extensions.

.. code:: bash

    tox -e pypy3

**GraalPy**

Tests with compatible extras (tornado, serial). Excludes extras that need C extensions GraalPy
doesn't support (glib, zmq) or that have known compatibility issues (trio, twisted). GraalPy also
ships no ``_curses`` module, so curses-dependent tests are expected to fail.

.. code:: bash

    tox -e graalpy311      # GraalPy 3.11
    tox -e graalpy312      # GraalPy 3.12

Supported Python versions
=========================

Urwid supports:

- CPython 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15
- CPython 3.13+ with free-threading (PEP 703 ``--disable-gil``)
- PyPy 3.x
- GraalPy 3.11, 3.12 (experimental)

Python implementation notes
===========================

**CPython (standard Python)**

Full support for all optional features. All extras (``curses``, ``glib``, ``serial``, ``tornado``, ``trio``, ``twisted``, ``zmq``) can be installed.

**CPython with Free-Threading (3.13, 3.14, 3.15+)**

Urwid core and pure-Python event loops are fully supported. Some extras require C extensions that may not have free-threading wheels available:

- ✅ Supported: core, tornado, trio, twisted (24.10.0+), serial, lcd
- ❌ Unsupported: glib, zmq (require C extensions with free-threading wheel support)

For free-threading Python, install with compatible extras:

.. code:: bash

    python3.13 -m pip install 'urwid[tornado,trio,serial]'

**PyPy**

Urwid core is fully supported. Some extras may have compatibility issues:

- ✅ Supported: core, tornado, trio, serial, lcd
- ⚠️ Limited: twisted (may have issues, test before using)
- ❌ Unsupported: glib, zmq (C extensions with limited PyPy support)

**GraalPy (experimental)**

Urwid core and the ``select``/``asyncio`` event loops are supported. Some extras and display
modules are not:

- ✅ Supported: core, tornado, serial, lcd
- ❌ Unsupported: curses (GraalPy ships no ``_curses`` module), glib, zmq, twisted, trio (no C
  extension support, or known compatibility issues)

Authors
=======

Creator
-------

`wardi <//github.com/wardi>`_

Maintainers
-----------

`and3rson <//github.com/and3rson>`_,
`tonycpsu <//github.com/tonycpsu>`_,
`ulidtko <//github.com/ulidtko>`_,
`penguinolog <//github.com/penguinolog>`_

Contributors
------------

`1in7billion <//github.com/1in7billion>`_,
`abadger <//github.com/abadger>`_,
`agrenott <//github.com/agrenott>`_,
`akorb <//github.com/akorb>`_,
`alethiophile <//github.com/alethiophile>`_,
`aleufroy <//github.com/aleufroy>`_,
`alobbs <//github.com/alobbs>`_,
`amjltc295 <//github.com/amjltc295>`_,
`and-semakin <//github.com/and-semakin>`_,
`andrewshadura <//github.com/andrewshadura>`_,
`andy-z <//github.com/andy-z>`_,
`anttin2020 <//github.com/anttin2020>`_,
`Apteryks <//github.com/Apteryks>`_,
`Arfrever <//github.com/Arfrever>`_,
`AutoAwesome <//github.com/AutoAwesome>`_,
`belak <//github.com/belak>`_,
`berney <//github.com/berney>`_,
`bk2204 <//github.com/bk2204>`_,
`BkPHcgQL3V <//github.com/BkPHcgQL3V>`_,
`bwesterb <//github.com/bwesterb>`_,
`carlos-jenkins <//github.com/carlos-jenkins>`_,
`Certseeds <//github.com/Certseeds>`_,
`Chipsterjulien <//github.com/Chipsterjulien>`_,
`chrisspen <//github.com/chrisspen>`_,
`cltrudeau <//github.com/cltrudeau>`_,
`Codeberg-AsGithubAlternative-buhtz <//github.com/Codeberg-AsGithubAlternative-buhtz>`_,
`cortesi <//github.com/cortesi>`_,
`d0c-s4vage <//github.com/d0c-s4vage>`_,
`derdon <//github.com/derdon>`_,
`dholth <//github.com/dholth>`_,
`dimays <//github.com/dimays>`_,
`dlo <//github.com/dlo>`_,
`dnaeon <//github.com/dnaeon>`_,
`doddo <//github.com/doddo>`_,
`douglas-larocca <//github.com/douglas-larocca>`_,
`drestebon <//github.com/drestebon>`_,
`dsotr <//github.com/dsotr>`_,
`dwf <//github.com/dwf>`_,
`EdwardBetts <//github.com/EdwardBetts>`_,
`elenril <//github.com/elenril>`_,
`EnricoBilla <//github.com/EnricoBilla>`_,
`extempore <//github.com/extempore>`_,
`fabiand <//github.com/fabiand>`_,
`floppym <//github.com/floppym>`_,
`flowblok <//github.com/flowblok>`_,
`fmoreau <//github.com/fmoreau>`_,
`goncalopp <//github.com/goncalopp>`_,
`Gordin <//github.com/Gordin>`_,
`GregIngelmo <//github.com/GregIngelmo>`_,
`grzaks <//github.com/grzaks>`_,
`gurupras <//github.com/gurupras>`_,
`HarveyHunt <//github.com/HarveyHunt>`_,
`Hoolean <//github.com/Hoolean>`_,
`hukka <//github.com/hukka>`_,
`hydratim <//github.com/hydratim>`_,
`ids1024 <//github.com/ids1024>`_,
`imrek <//github.com/imrek>`_,
`isovector <//github.com/isovector>`_,
`itaisod <//github.com/itaisod>`_,
`ixxra <//github.com/ixxra>`_,
`jeblair <//github.com/jeblair>`_,
`johndeaton <//github.com/johndeaton>`_,
`jonblack <//github.com/jonblack>`_,
`jspricke <//github.com/jspricke>`_,
`kedder <//github.com/kedder>`_,
`Kelketek <//github.com/Kelketek>`_,
`KennethNielsen <//github.com/KennethNielsen>`_,
`kesipyc <//github.com/kesipyc>`_,
`kkrolczyk <//github.com/kkrolczyk>`_,
`Kwpolska <//github.com/Kwpolska>`_,
`Lahorde <//github.com/Lahorde>`_,
`laike9m <//github.com/laike9m>`_,
`larsks <//github.com/larsks>`_,
`lfam <//github.com/lfam>`_,
`lgbaldoni <//github.com/lgbaldoni>`_,
`lighth7015 <//github.com/lighth7015>`_,
`livibetter <//github.com/livibetter>`_,
`Lothiraldan <//github.com/Lothiraldan>`_,
`Mad-ness <//github.com/Mad-ness>`_,
`madebr <//github.com/madebr>`_,
`magniff <//github.com/magniff>`_,
`marlox-ouda <//github.com/marlox-ouda>`_,
`mattymo <//github.com/mattymo>`_,
`mdtrooper <//github.com/mdtrooper>`_,
`mgk <//github.com/mgk>`_,
`mimi1vx <//github.com/mimi1vx>`_,
`mobyte0 <//github.com/mobyte0>`_,
`MonAaraj <//github.com/MonAaraj>`_,
`MonthlyPython <//github.com/MonthlyPython>`_,
`mountainstorm <//github.com/mountainstorm>`_,
`mselee <//github.com/mselee>`_,
`mwhudson <//github.com/mwhudson>`_,
`naquad <//github.com/naquad>`_,
`nchavez324 <//github.com/nchavez324>`_,
`neumond <//github.com/neumond>`_,
`nolash <//github.com/nolash>`_,
`ntamas <//github.com/ntamas>`_,
`nyov <//github.com/nyov>`_,
`ocarneiro <//github.com/ocarneiro>`_,
`okayzed <//github.com/okayzed>`_,
`pquentin <//github.com/pquentin>`_,
`rbanffy <//github.com/rbanffy>`_,
`ReddyKilowatt <//github.com/ReddyKilowatt>`_,
`regebro <//github.com/regebro>`_,
`renegarcia <//github.com/renegarcia>`_,
`rianhunter <//github.com/rianhunter>`_,
`roburban <//github.com/roburban>`_,
`RRMoelker <//github.com/RRMoelker>`_,
`rwarren <//github.com/rwarren>`_,
`scopatz <//github.com/scopatz>`_,
`seanhussey <//github.com/seanhussey>`_,
`seonon <//github.com/seonon>`_,
`shadedKE <//github.com/shadedKE>`_,
`sithglan <//github.com/sithglan>`_,
`Sjc1000 <//github.com/Sjc1000>`_,
`sporkexec <//github.com/sporkexec>`_,
`squrky <//github.com/squrky>`_,
`ssbr <//github.com/ssbr>`_,
`techdragon <//github.com/techdragon>`_,
`thehunmonkgroup <//github.com/thehunmonkgroup>`_,
`thisch <//github.com/thisch>`_,
`thornycrackers <//github.com/thornycrackers>`_,
`TomasTomecek <//github.com/TomasTomecek>`_,
`tompickering <//github.com/tompickering>`_,
`tony <//github.com/tony>`_,
`ttanner <//github.com/ttanner>`_,
`tu500 <//github.com/tu500>`_,
`uSpike <//github.com/uSpike>`_,
`vega0 <//github.com/vega0>`_,
`vit1251 <//github.com/vit1251>`_,
`waveform80 <//github.com/waveform80>`_,
`Wesmania <//github.com/Wesmania>`_,
`xandfury <//github.com/xandfury>`_,
`xndcn <//github.com/xndcn>`_,
`zhongshangwu <//github.com/zhongshangwu>`_,
`zrax <//github.com/zrax>`_


.. |pypi| image:: https://img.shields.io/pypi/v/urwid
    :alt: current version on PyPi
    :target: https://pypi.python.org/pypi/urwid

.. |docs| image:: https://github.com/urwid/urwid/actions/workflows/documentation.yml/badge.svg?branch=master
    :alt: Documentation Status
    :target: https://urwid.org

.. |gitter| image:: https://img.shields.io/gitter/room/urwid/community
   :alt: Gitter
   :target: https://gitter.im/urwid/community

.. |ci| image:: https://github.com/urwid/urwid/actions/workflows/pythonpackage.yml/badge.svg?branch=master
    :target: https://github.com/urwid/urwid/actions
    :alt: CI status

.. |pre-commit| image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

.. |coveralls| image:: https://coveralls.io/repos/github/urwid/urwid/badge.svg
    :alt: test coverage
    :target: https://coveralls.io/github/urwid/urwid
