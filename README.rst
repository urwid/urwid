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
- Compatible with Python 2.7, 3.5+ and PyPy

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

Authors
-------

`abadger <//github.com/abadger>`_,
`aglyzov <//github.com/aglyzov>`_,
`agrenott <//github.com/agrenott>`_,
`akosthekiss <//github.com/akosthekiss>`_,
`alexozer <//github.com/alexozer>`_,
`alobbs <//github.com/alobbs>`_,
`and-semakin <//github.com/and-semakin>`_,
`andersk <//github.com/andersk>`_,
`andrewshadura <//github.com/andrewshadura>`_,
`aszlig <//github.com/aszlig>`_,
`BkPHcgQL3V <//github.com/BkPHcgQL3V>`_,
`carlos-jenkins <//github.com/carlos-jenkins>`_,
`d0c-s4vage <//github.com/d0c-s4vage>`_,
`dnaeon <//github.com/dnaeon>`_,
`drestebon <//github.com/drestebon>`_,
`EdwardBetts <//github.com/EdwardBetts>`_,
`eevee <//github.com/eevee>`_,
`elenril <//github.com/elenril>`_,
`extempore <//github.com/extempore>`_,
`fabiand <//github.com/fabiand>`_,
`federicotdn <//github.com/federicotdn>`_,
`floppym <//github.com/floppym>`_,
`garrison <//github.com/garrison>`_,
`geier <//github.com/geier>`_,
`grzaks <//github.com/grzaks>`_,
`hootnot <//github.com/hootnot>`_,
`horazont <//github.com/horazont>`_,
`ids1024 <//github.com/ids1024>`_,
`inducer <//github.com/inducer>`_,
`ismail-s <//github.com/ismail-s>`_,
`ivanov <//github.com/ivanov>`_,
`jeblair <//github.com/jeblair>`_,
`Julian <//github.com/Julian>`_,
`jwilk <//github.com/jwilk>`_,
`kedder <//github.com/kedder>`_,
`KennethNielsen <//github.com/KennethNielsen>`_,
`kkrolczyk <//github.com/kkrolczyk>`_,
`larsks <//github.com/larsks>`_,
`Lothiraldan <//github.com/Lothiraldan>`_,
`matthijskooijman <//github.com/matthijskooijman>`_,
`mattymo <//github.com/mattymo>`_,
`mbarkhau <//github.com/mbarkhau>`_,
`mgk <//github.com/mgk>`_,
`mimi1vx <//github.com/mimi1vx>`_,
`mobyte0 <//github.com/mobyte0>`_,
`mwhudson <//github.com/mwhudson>`_,
`nchavez324 <//github.com/nchavez324>`_,
`neumond <//github.com/neumond>`_,
`nocarryr <//github.com/nocarryr>`_,
`ntamas <//github.com/ntamas>`_,
`olleolleolle <//github.com/olleolleolle>`_,
`pazz <//github.com/pazz>`_,
`pniedzwiedzinski <//github.com/pniedzwiedzinski>`_,
`raek <//github.com/raek>`_,
`renegarcia <//github.com/renegarcia>`_,
`rianhunter <//github.com/rianhunter>`_,
`rndusr <//github.com/rndusr>`_,
`rr- <//github.com/rr->`_,
`rwarren <//github.com/rwarren>`_,
`seanhussey <//github.com/seanhussey>`_,
`Sjc1000 <//github.com/Sjc1000>`_,
`ssbr <//github.com/ssbr>`_,
`tdryer <//github.com/tdryer>`_,
`techtonik <//github.com/techtonik>`_,
`tompickering <//github.com/tompickering>`_,
`tu500 <//github.com/tu500>`_,
`uSpike <//github.com/uSpike>`_,
`usrlocalben <//github.com/usrlocalben>`_,
`waveform80 <//github.com/waveform80>`_,
`wernight <//github.com/wernight>`_,
`Wesmania <//github.com/Wesmania>`_,
`westurner <//github.com/westurner>`_,
`winbornejw <//github.com/winbornejw>`_,
`xndcn <//github.com/xndcn>`_,
`xnox <//github.com/xnox>`_,
`zrax <//github.com/zrax>`_

Contributors
------------

`aleufroy <//github.com/aleufroy>`_,
`andy-z <//github.com/andy-z>`_,
`anttin2020 <//github.com/anttin2020>`_,
`belak <//github.com/belak>`_,
`berney <//github.com/berney>`_,
`bk2204 <//github.com/bk2204>`_,
`bukzor <//github.com/bukzor>`_,
`Chipsterjulien <//github.com/Chipsterjulien>`_,
`chrisspen <//github.com/chrisspen>`_,
`dimays <//github.com/dimays>`_,
`dlo <//github.com/dlo>`_,
`douglas-larocca <//github.com/douglas-larocca>`_,
`goncalopp <//github.com/goncalopp>`_,
`Gordin <//github.com/Gordin>`_,
`grugq <//github.com/grugq>`_,
`hkoof <//github.com/hkoof>`_,
`Hoolean <//github.com/Hoolean>`_,
`hukka <//github.com/hukka>`_,
`itaisod <//github.com/itaisod>`_,
`ixxra <//github.com/ixxra>`_,
`Kelketek <//github.com/Kelketek>`_,
`livibetter <//github.com/livibetter>`_,
`marlox-ouda <//github.com/marlox-ouda>`_,
`MonAaraj <//github.com/MonAaraj>`_,
`mountainstorm <//github.com/mountainstorm>`_,
`mselee <//github.com/mselee>`_,
`nyov <//github.com/nyov>`_,
`pquentin <//github.com/pquentin>`_,
`RRMoelker <//github.com/RRMoelker>`_,
`shadedKE <//github.com/shadedKE>`_,
`sitaktif <//github.com/sitaktif>`_,
`sporkexec <//github.com/sporkexec>`_,
`thehunmonkgroup <//github.com/thehunmonkgroup>`_,
`thisch <//github.com/thisch>`_,
`TomasTomecek <//github.com/TomasTomecek>`_,
`ttanner <//github.com/ttanner>`_,
`vega0 <//github.com/vega0>`_


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
