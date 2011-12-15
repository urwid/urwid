:mod:`urwid.listbox` --- Listbox
================================

.. module:: urwid.listbox
   :synopsis: Listbox

.. exception:: ListWalkerError

   todo

.. class:: ListWalker

   todo

.. class:: SimpleListWalker(contents)

   *contents* -- list to copy into this object
   
   Changes made to this object (when it is treated as a list) are detected
   automatically and will cause ListBox objects using this list walker to be
   updated.

   .. method:: set_modified_callback(callback)

      This function inherited from MonitoredList is not implemented in
      SimleListWalker.
      
      Use connect_signal(list_walker, "modified", ...) instead.

   .. method:: get_focus()

      Return (focus widget, focus position).

   .. method:: set_focus(position)

      Set focus position.

   .. method:: get_next(start_from)

      Return (widget after start_from, position after start_from).

   .. method:: get_prev(start_from)

      Return (widget before start_from, position before start_from).


.. exception:: ListBoxError

   todo

.. class:: ListBox(body)

   *body* is a :class:`ListWalker`-like object that contains widgets to be
   displayed inside the list box


   .. method:: calculate_visible(size[, focus=False])

      Return ``(middle, top, bottom)`` or ``None, None, None``.

      *middle* -- (row offset (when +ve) or inset (when -ve), focus widget,
      focus position, focus rows, cursor coords or None )

      *top* -- ( # lines to trim off top, list of (widget, position, rows)
      tuples above focus in order from bottom to top )

      *bottom* -- ( # lines to trim off bottom, list of (widget, position,
      rows) tuples below focus in order from top to bottom )

   .. method:: render(size[, focus=False])

      Render listbox and return canvas.

   .. method:: get_cursor_coords(size)

      todo

   .. method:: set_focus_valign(valign)

      Set the focus widget's display offset and inset.

      *valign* -- one of:
          'top', 'middle', 'bottom'
          ('fixed top', rows)
          ('fixed bottom', rows)
          ('relative', percentage 0=top 100=bottom)

   .. method:: set_focus(position[, coming_from=None])

      Set the focus position and try to keep the old focus in view.

      *position* -- a position compatible with ``self.body.set_focus``

      *coming_from* -- set to 'above' or 'below' if you know that old position
      is above or below the new position.

   .. method:: get_focus()

      Return a ``(focus widget, focus position)`` tuple.

   .. method:: shift_focus(size, offset_inset)

      Move the location of the current focus relative to the top.

      *offset_inset* -- either the number of rows between the top of the
      listbox and the start of the focus widget (+ve value) or the number of
      lines of the focus widget hidden off the top edge of the listbox (-ve
      value) or 0 if the top edge of the focus widget is aligned with the top
      edge of the listbox

   .. method:: update_pref_col_from_focus(size)

      Update ``self.pref_col`` from the focus widget.

   .. method:: change_focus(size, position[, offset_inset=0, \
                            coming_from=None, cursor_coords=None, \
                            snap_rows=None])

      Change the current focus widget.
      
      *position* -- a position compatible with ``self.body.set_focus``.

      *offset_inset* -- either the number of rows between the top of the
      listbox and the start of the focus widget (+ve value) or the number of
      lines of the focus widget hidden off the top edge of the listbox (-ve
      value) or 0 if the top edge of the focus widget is aligned with the top
      edge of the listbox (default if unspecified)

      *coming_from* -- eiter 'above', 'below' or unspecified (``None``).

      *cursor_coords* -- ``(x, y)`` tuple indicating the desired column and row
      for the cursor, a ``(x,)`` tuple indicating only the column for the cursor,
      or unspecified (``None``).

      *snap_rows* -- the maximum number of extra rows to scroll when trying to
      "snap" a selectable focus into the view.

   .. method:: get_focus_offset_inset(size)

      Return ``(offset rows, inset rows)`` for focus widget.

   .. method:: make_cursor_visible(size)

      Shift the focus widget so that its cursor is visible.

   .. method:: keypress(size, key)

      Move selection through the list elements scrolling when necessary. 'up'
      and 'down' are first passed to widget in focus in case that widget can
      handle them. 'page up' and 'page down' are always handled by the ListBox.
      
      Keystrokes handled by this widget are:
      'up'        up one line (or widget)
      'down'      down one line (or widget)
      'page up'   move cursor up one listbox length
      'page down' move cursor down one listbox length


   .. method:: mouse_event(size, event, button, col, row, focus)

      Pass the event to the contained widgets. May change focus on button 1
      press.

   .. method:: ends_visible(size[, focus=False])

      Return a list that may contain 'top' and/or 'bottom'.
 
      Convenience function for checking whether the top and bottom of the
      list are visible
