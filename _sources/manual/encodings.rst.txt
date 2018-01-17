.. vim: set fileencoding=utf-8:

.. _text-encodings:

***********************
  Encodings Supported
***********************

.. currentmodule:: urwid

Urwid has a single global setting for text encoding that is set on start-up
based on the configured locale. You may change that setting with the
:meth:`set_encoding` method. eg.

::

    urwid.set_encoding("UTF-8")

There are two distinct modes of handling encodings with Urwid: Unicode or
Pass-through. The mode corresponds to using Unicode strings or normal strings
in your widgets.

::

    txt_a = urwid.Text(u"El Niño")
    txt_b = urwid.Text("El Niño")

``txt_a`` will be automatically encoded when it is displayed (Unicode mode).

``txt_b`` is **assumed** to be in the encoding the user is expecting and passed
through as-is (Pass-through mode). If the encodings are different then the
user will see "mojibake" (garbage) on their screen.

The only time it makes sense to use pass-through mode is if you're handling an
encoding that does not round-trip to Unicode properly, or if you're absolutely
sure you know what you're doing.

Unicode Support
===============

Urwid has a basic understanding of character widths so that the text layout
code can properly wrap and display most text. There is currently no support for
right-to-left text.

You should be able to use any valid Unicode characters that are present in the
global encoding setting in your widgets, with the addition of some common DEC
graphic characters:

::

    \u00A3 (£), \u00B0 (°), \u00B1 (±), \u00B7 (·), \u03C0 (π),
    \u2260 (≠), \u2264 (≤), \u2265 (≥), \u23ba (⎺), \u23bb (⎻),
    \u23bc (⎼), \u23bd (⎽), \u2500 (─), \u2502 (│), \u250c (┌),
    \u2510 (┐), \u2514 (└), \u2518 (┘), \u251c (├), \u2524 (┤),
    \u252c (┬), \u2534 (┴), \u253c (┼), \u2592 (▒), \u25c6 (◆)

If you use these characters with a non-UTF-8 encoding they will be sent using
the alternate character set sequences supported by some terminals.

Pass-through Support
====================

Supported encodings for pass-through mode:

* UTF-8 (narrow and wide characters)
* ISO-8859-*
* EUC-JP (JISX 0208 only)
* EUC-KR
* EUC-CN (aka CN-GB)
* EUC-TW (CNS 11643 plain 1 only)
* GB2312
* GBK
* BIG5
* UHC

In pass-through mode Urwid must still calculate character widths. For UTF-8
mode the widths are specified in the Unicode standard. For ISO-8859-* all
bytes are assumed to be 1 column wide characters. For the remaining supported
encodings any byte with the high-bit set is considered to be half of a 2-column
wide character.

The additional plains in EUC are not currently supported.

Future Work
===========

Text encoding should be a per-screen (display module) setting, not a global
setting. It should be possible to simultaneously support different encodings on
different screens with Urwid. Making this work involves possibly changing the
function signature of many widget methods, because encoding needs to be
specified along with size and focus.

Device-specific encodings should also be possible for Unicode mode. The LCD
display module in development drives a device with a non-standard mapping of
Unicode code points to 8-bit values, but it should still be possible to use a
Unicode text to display the characters it supports.
