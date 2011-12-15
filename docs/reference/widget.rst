:mod:`urwid.widget` --- Widgets
===============================

.. module:: urwid.widget
   :synopsis: Widgets

..
   # Widget sizing methods
   # (use the same string objects to make some comparisons faster)
   FLOW = 'flow'
   BOX = 'box'
   FIXED = 'fixed'
   
   # Text alignment modes 
   LEFT = 'left'
   RIGHT = 'right'
   CENTER = 'center'
   
   # Filler alignment modes 
   TOP = 'top'
   MIDDLE = 'middle'
   BOTTOM = 'bottom'
   
   # Text wrapping modes
   SPACE = 'space'
   ANY = 'any'
   CLIP = 'clip'
   
   # Extras for Padding
   PACK = 'pack'
   GIVEN = 'given'
   RELATIVE = 'relative'
   RELATIVE_100 = (RELATIVE, 100)


.. class:: WidgetMeta

    Automatic caching of render and rows methods.

    Class variable ``no_cache`` is a list of names of methods to not cache.
    Class variable ``ignore_focus`` if defined and ``True`` indicates that this
    widget is not affected by the focus parameter, so it may be ignored when
    caching.

.. exception:: WidgetError

   todo

.. function:: validate_size(widget, size, canv)

   Raise a WidgetError if a canv does not match size size.

.. function:: update_wrapper(new_fn, fn)

   Copy as much of the function detail from fn to new_fn as we can.

.. function:: cache_widget_render(cls)

   Return a function that wraps the cls.render() method and fetches and stores
   canvases with CanvasCache.

.. function:: nocache_widget_render(cls)

   Return a function that wraps the cls.render() method and finalizes the
   canvas that it returns.

.. function:: nocache_widget_render_instance(self)

   Return a function that wraps the cls.render() method and finalizes the
   canvas that it returns, but does not cache the canvas.

.. function:: cache_widget_rows(cls)

   Return a function that wraps the cls.rows() method and returns rows from the
   CanvasCache if available.


.. class:: Widget
    
   base class of widgets

   .. attribute:: _sizing
    
      Default to ``set([])``.

   .. attribute:: _command_map
    
      Default to the single shared :class:`~urwid.command_map.CommandMap`.

   .. method:: _emit(name, *args)

      Convenience function to emit signals with self as first argument.
    
   .. method:: selectable()

      Return ``True`` if this widget should take focus. Default implementation
      returns the value of ``self._selectable``.
    
   .. method:: sizing()

      Return a set including one or more of ``box``, ``flow`` and ``fixed``.
      Default implementation returns the value of ``self._sizing``.

   .. method:: pack(size[, focus=False])

      Return a "packed" ``(maxcol, maxrow)`` for this widget. Default
      implementation (no packing defined) returns size, and calculates maxrow
      if not given.

   .. attribute:: base_widget

      This property returns the widget without any decorations, default
      implementation returns self.


.. class:: FlowWidget

   Base class of widgets that determine their rows from the number of columns
   available.
    
   .. method:: rows(size[, focus=False])

      All flow widgets must implement this function.

   .. method:: render(size[, focus=False])

      All widgets must implement this function.


.. class:: BoxWidget

   Base class of width and height constrained widgets such as the top level
   widget attached to the display object.

.. function:: fixed_size(size)

   raise ValueError if size != ().
    
   Used by FixedWidgets to test size parameter.


.. class:: FixedWidget

   Base class of widgets that know their width and height and cannot be resized

    
   .. method:: pack([size=None, focus=False])

      All fixed widgets must implement this function.

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
