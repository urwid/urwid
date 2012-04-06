Basic Widgets
=============

.. class:: Divider([div_char=u" ", top=0, bottom=0])

   Horizontal divider widget

   Create a horizontal divider widget.

   *div_char* -- character to repeat across line

   *top* -- number of blank lines above

   *bottom* -- number of blank lines below

   ignore_focus = True


.. class:: SolidFill([fill_char=" "])

   Create a box widget that will fill an area with a single character.

   *fill_char* -- character to fill area with


.. exception:: TextError

   todo


.. class:: Text(self, markup[, align=LEFT, wrap=SPACE, layout=None])

   A horizontally resizeable text widget.

   *markup* -- content of text widget, one of:

       * plain string -- string is displayed

       * ``(attr, markup2)`` -- markup2 is given attribute attr

       * ``[markupA, markupB, ...]`` -- list items joined together

   *align* -- align mode for text layout

   *wrap* -- wrap mode for text layout

   *layout* -- layout object to use, defaults to StandardTextLayout

   .. method:: def set_text(markup)

      Set content of text widget.

   .. method:: get_text()

      Returns ``(text, attributes)``.

      *text* -- complete string content (unicode) of text widget

      *attributes* -- run length encoded attributes for text

   .. attribute:: text

   .. attribute:: attrib

   .. method:: set_align_mode(mode)

      Set text alignment/justification. Valid modes for StandardTextLayout are:
      ``'left'``, ``'center'`` and ``'right'``.

   .. method:: set_wrap_mode(mode)
      
      Set wrap mode.

   .. method:: set_layout(align, wrap[, layout=None])

      Set layout object, align and wrap modes:

      *align* -- align mode for text layout

      *wrap* -- wrap mode for text layout

      *layout* -- layout object to use, defaults to StandardTextLayout

   .. attribute:: align

   .. attribute:: wrap

   .. attribute:: layout

   .. method:: get_line_translation(maxcol[, ta=None])

      Return layout structure used to map self.text to a canvas. This method
      is used internally, but may be useful for debugging custom layout
      classes.


.. exception:: EditError

   todo


.. class:: Edit([caption=u"", edit_text=u"", multiline=False, align=LEFT, \
                wrap=SPACE, allow_tab=False, edit_pos=None, layout=None, \
                mask=None])

   Text editing widget implements cursor movement, text insertion and deletion.
   A caption may prefix the editing area. Uses text class for text layout.

   *caption* -- markup for caption preceeding edit_text

   *edit_text* -- text string for editing

   *multiline* -- True: 'enter' inserts newline False: return it

   *align* -- align mode

   *wrap* -- wrap mode

   *allow_tab* -- True: 'tab' inserts 1-8 spaces False: return it

   *edit_pos* -- initial position for cursor, None:at end

   *layout* -- layout object

   *mask* -- character to mask away text with, None means no masking

   signals = ["change"]

   .. method:: valid_char(ch)

      Return true for printable characters.
    
   .. method:: update_text()

      No longer supported.

   .. method:: set_caption(caption)

      Set the caption markup for this widget.

      *caption* -- see ``Text.__init__()`` for description of markup


