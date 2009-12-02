#!/usr/bin/python
#
# Urwid Window-Icon-Menu-Pointer-style widget classes
#    Copyright (C) 2004-2008  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

from widget import *
from container import *
from command_map import command_map


class SelectableIcon(Text):
    _selectable = True
    def __init__(self, text, cursor_position=1):
        """
        text -- markup for this widget
        cursor_position -- position the cursor will appear in when this
            widget is in focus

        This is a text widget that is selectable with a cursor
        displayed at a fixed location in the text when in focus
        """
        self.__super.__init__(text)
        self._cursor_position = cursor_position
    
    def render(self, size, focus=False):
        """
        Render the text content of this widget with a cursor when
        in focus.

        >>> si = SelectableIcon("[!]")
        >>> si
        <SelectableIcon selectable flow widget '[!]'>
        >>> si.render((4,), focus=True).cursor
        (1, 0)
        >>> si = SelectableIcon("((*))", 2)
        >>> si.render((8,), focus=True).cursor
        (2, 0)
        >>> si.render((2,), focus=True).cursor
        (0, 1)
        """
        c = self.__super.render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c
    
    def get_cursor_coords(self, size):
        """
        Return the position of the cursor if visible.  This method
        is required for widgets that display a cursor.
        """
        if self._cursor_position > len(self.text):
            return None
        # find out where the cursor will be displayed based on
        # the text layout
        (maxcol,) = size
        trans = self.get_line_translation(maxcol)
        x, y = calc_coords(self.text, trans, self._cursor_position)
        return x, y

    def keypress(self, size, key):
        """
        No keys are handled by this widget.  This method is
        required for selectable widgets.
        """
        return key

class CheckBoxError(Exception):
    pass

class CheckBox(WidgetWrap):
    states = { 
        True: SelectableIcon("[X]"),
        False: SelectableIcon("[ ]"),
        'mixed': SelectableIcon("[#]") }
    reserve_columns = 4

    # allow users of this class to listen for change events
    # sent when the state of this widget is modified
    # (this variable is picked up by the MetaSignals metaclass)
    signals = ["change"]
    
    def __init__(self, label, state=False, has_mixed=False,
             on_state_change=None, user_data=None):
        """
        label -- markup for check box label
        state -- False, True or "mixed"
        has_mixed -- True if "mixed" is a state to cycle through
        on_state_change, user_data -- shorthand for connect_signal()
            function call for a single callback
        
        Signals supported: 'change'
        Register signal handler with:
          connect_signal(check_box, 'change', callback [,user_data])
        where callback is callback(check_box, new_state [,user_data])
        Unregister signal handlers with:
          disconnect_signal(check_box, 'change', callback [,user_data])

        >>> CheckBox("Confirm")
        <CheckBox selectable widget 'Confirm' state=False>
        >>> CheckBox("Yogourt", "mixed", True)
        <CheckBox selectable widget 'Yogourt' state='mixed'>
        >>> cb = CheckBox("Extra onions", True)
        >>> cb
        <CheckBox selectable widget 'Extra onions' state=True>
        >>> cb.render((20,), focus=True).text  # preview CheckBox
        ['[X] Extra onions    ']
        """
        self.__super.__init__(None) # self.w set by set_state below
        self._label = Text("")
        self.has_mixed = has_mixed
        self._state = None
        # The old way of listening for a change was to pass the callback
        # in to the constructor.  Just convert it to the new way:
        if on_state_change:
            connect_signal(self, 'change', on_state_change, user_data)
        self.set_label(label)
        self.set_state(state)
    
    def _repr_words(self):
        return self.__super._repr_words() + [
            repr(self.label)]
    
    def _repr_attrs(self):
        return dict(self.__super._repr_attrs(),
            state=self.state)
    
    def set_label(self, label):
        """
        Change the check box label.

        label -- markup for label.  See Text widget for description
        of text markup.

        >>> cb = CheckBox("foo")
        >>> cb
        <CheckBox selectable widget 'foo' state=False>
        >>> cb.set_label(('bright_attr', "bar"))
        >>> cb
        <CheckBox selectable widget 'bar' state=False>
        """
        self._label.set_text(label)
        # no need to call self._invalidate(). WidgetWrap takes care of
        # that when self.w changes
    
    def get_label(self):
        """
        Return label text.

        >>> cb = CheckBox("Seriously")
        >>> cb.get_label()
        'Seriously'
        >>> cb.label  # Urwid 0.9.9 or later
        'Seriously'
        >>> cb.set_label([('bright_attr', "flashy"), " normal"])
        >>> cb.label  #  only text is returned 
        'flashy normal'
        """
        return self._label.text
    label = property(get_label)
    
    def set_state(self, state, do_callback=True):
        """
        Set the CheckBox state.

        state -- True, False or "mixed"
        do_callback -- False to supress signal from this change
        
        >>> changes = []
        >>> def callback_a(cb, state, user_data): 
        ...     changes.append("A %r %r" % (state, user_data))
        >>> def callback_b(cb, state): 
        ...     changes.append("B %r" % state)
        >>> cb = CheckBox('test', False, False)
        >>> connect_signal(cb, 'change', callback_a, "user_a")
        >>> connect_signal(cb, 'change', callback_b)
        >>> cb.set_state(True) # both callbacks will be triggered
        >>> cb.state
        True
        >>> disconnect_signal(cb, 'change', callback_a, "user_a")
        >>> cb.state = False  # Urwid 0.9.9 or later
        >>> cb.state
        False
        >>> cb.set_state(True)
        >>> cb.state
        True
        >>> cb.set_state(False, False) # don't send signal
        >>> changes
        ["A True 'user_a'", 'B True', 'B False', 'B True']
        """
        if self._state == state:
            return

        if state not in self.states:
            raise CheckBoxError("%s Invalid state: %s" % (
                repr(self), repr(state)))

        # self._state is None is a special case when the CheckBox
        # has just been created
        if do_callback and self._state is not None:
            self._emit('change', state)
        self._state = state
        # rebuild the display widget with the new state
        self._w = Columns( [
            ('fixed', self.reserve_columns, self.states[state] ),
            self._label ] )
        self._w.focus_col = 0
        
    def get_state(self):
        """Return the state of the checkbox."""
        return self._state
    state = property(get_state, set_state)
        
    def keypress(self, size, key):
        """
        Toggle state on 'activate' command.  

        >>> assert command_map[' '] == 'activate'
        >>> assert command_map['enter'] == 'activate'
        >>> size = (10,)
        >>> cb = CheckBox('press me')
        >>> cb.state
        False
        >>> cb.keypress(size, ' ')
        >>> cb.state
        True
        >>> cb.keypress(size, ' ')
        >>> cb.state
        False
        """
        if command_map[key] != 'activate':
            return key
        
        self.toggle_state()
        
    def toggle_state(self):
        """
        Cycle to the next valid state.
        
        >>> cb = CheckBox("3-state", has_mixed=True)
        >>> cb.state
        False
        >>> cb.toggle_state()
        >>> cb.state
        True
        >>> cb.toggle_state()
        >>> cb.state
        'mixed'
        >>> cb.toggle_state()
        >>> cb.state
        False
        """
        if self.state == False:
            self.set_state(True)
        elif self.state == True:
            if self.has_mixed:
                self.set_state('mixed')
            else:
                self.set_state(False)
        elif self.state == 'mixed':
            self.set_state(False)

    def mouse_event(self, size, event, button, x, y, focus):
        """
        Toggle state on button 1 press.
        
        >>> size = (20,)
        >>> cb = CheckBox("clickme")
        >>> cb.state
        False
        >>> cb.mouse_event(size, 'mouse press', 1, 2, 0, True)
        True
        >>> cb.state
        True
        """
        if button != 1 or not is_mouse_press(event):
            return False
        self.toggle_state()
        return True
    
        
class RadioButton(CheckBox):
    states = { 
        True: SelectableIcon("(X)"),
        False: SelectableIcon("( )"),
        'mixed': SelectableIcon("(#)") }
    reserve_columns = 4

    def __init__(self, group, label, state="first True",
             on_state_change=None, user_data=None):
        """
        group -- list for radio buttons in same group
        label -- markup for radio button label
        state -- False, True, "mixed" or "first True"
        on_state_change, user_data -- shorthand for connect_signal()
            function call for a single 'change' callback

        This function will append the new radio button to group.
        "first True" will set to True if group is empty.
        
        Signals supported: 'change'
        Register signal handler with:
          connect_signal(radio_button, 'change', callback [,user_data])
        where callback is callback(radio_button, new_state [,user_data])
        Unregister signal handlers with:
          disconnect_signal(radio_button, 'change', callback [,user_data])

        >>> bgroup = [] # button group
        >>> b1 = RadioButton(bgroup, "Agree")
        >>> b2 = RadioButton(bgroup, "Disagree")
        >>> len(bgroup)
        2
        >>> b1
        <RadioButton selectable widget 'Agree' state=True>
        >>> b2
        <RadioButton selectable widget 'Disagree' state=False>
        >>> b2.render((15,), focus=True).text  # preview RadioButton
        ['( ) Disagree   ']
        """
        if state=="first True":
            state = not group
        
        self.group = group
        self.__super.__init__(label, state, False, on_state_change, 
            user_data)
        group.append(self)
    

    
    def set_state(self, state, do_callback=True):
        """
        Set the RadioButton state.

        state -- True, False or "mixed"
        do_callback -- False to supress signal from this change

        If state is True all other radio buttons in the same button
        group will be set to False.

        >>> bgroup = [] # button group
        >>> b1 = RadioButton(bgroup, "Agree")
        >>> b2 = RadioButton(bgroup, "Disagree")
        >>> b3 = RadioButton(bgroup, "Unsure")
        >>> b1.state, b2.state, b3.state
        (True, False, False)
        >>> b2.set_state(True)
        >>> b1.state, b2.state, b3.state
        (False, True, False)
        >>> def relabel_button(radio_button, new_state):
        ...     radio_button.set_label("Think Harder!")
        >>> connect_signal(b3, 'change', relabel_button)
        >>> b3
        <RadioButton selectable widget 'Unsure' state=False>
        >>> b3.set_state(True) # this will trigger the callback
        >>> b3
        <RadioButton selectable widget 'Think Harder!' state=True>
        """
        if self._state == state:
            return

        self.__super.set_state(state, do_callback)

        # if we're clearing the state we don't have to worry about
        # other buttons in the button group
        if state is not True:
            return

        # clear the state of each other radio button
        for cb in self.group:
            if cb is self: continue
            if cb._state:
                cb.set_state(False)
    
    
    def toggle_state(self):
        """
        Set state to True.
        
        >>> bgroup = [] # button group
        >>> b1 = RadioButton(bgroup, "Agree")
        >>> b2 = RadioButton(bgroup, "Disagree")
        >>> b1.state, b2.state
        (True, False)
        >>> b2.toggle_state()
        >>> b1.state, b2.state
        (False, True)
        >>> b2.toggle_state()
        >>> b1.state, b2.state
        (False, True)
        """
        self.set_state(True)

            

class Button(WidgetWrap):
    button_left = Text("<")
    button_right = Text(">")

    signals = ["click"]
    
    def __init__(self, label, on_press=None, user_data=None):
        """
        label -- markup for button label
        on_press, user_data -- shorthand for connect_signal()
            function call for a single callback
        
        Signals supported: 'click'
        Register signal handler with:
          connect_signal(button, 'click', callback [,user_data])
        where callback is callback(button [,user_data])
        Unregister signal handlers with:
          disconnect_signal(button, 'click', callback [,user_data])

        >>> Button("Ok")
        <Button selectable widget 'Ok'>
        >>> b = Button("Cancel")
        >>> b.render((15,), focus=True).text  # preview Button
        ['< Cancel      >']
        """
        self._label = SelectableIcon("", 0)    
        cols = Columns([
            ('fixed', 1, self.button_left),
            self._label,
            ('fixed', 1, self.button_right)],
            dividechars=1)
        self.__super.__init__(cols) 
        
        # The old way of listening for a change was to pass the callback
        # in to the constructor.  Just convert it to the new way:
        if on_press:
            connect_signal(self, 'click', on_press, user_data)

        self.set_label(label)
    
    def _repr_words(self):
        # include button.label in repr(button)
        return self.__super._repr_words() + [
            repr(self.label)]

    def set_label(self, label):
        """
        Change the button label.

        label -- markup for button label

        >>> b = Button("Ok")
        >>> b.set_label("Yup yup")
        >>> b
        <Button selectable widget 'Yup yup'>
        """
        self._label.set_text(label)
    
    def get_label(self):
        """
        Return label text.

        >>> b = Button("Ok")
        >>> b.get_label()
        'Ok'
        >>> b.label  # Urwid 0.9.9 or later
        'Ok'
        """
        return self._label.text
    label = property(get_label)
    
    def keypress(self, size, key):
        """
        Send 'click' signal on 'activate' command.
        
        >>> assert command_map[' '] == 'activate'
        >>> assert command_map['enter'] == 'activate'
        >>> size = (15,)
        >>> b = Button("Cancel")
        >>> clicked_buttons = []
        >>> def handle_click(button):
        ...     clicked_buttons.append(button.label)
        >>> connect_signal(b, 'click', handle_click)
        >>> b.keypress(size, 'enter')
        >>> b.keypress(size, ' ')
        >>> clicked_buttons
        ['Cancel', 'Cancel']
        """
        if command_map[key] != 'activate':
            return key

        self._emit('click')

    def mouse_event(self, size, event, button, x, y, focus):
        """
        Send 'click' signal on button 1 press.

        >>> size = (15,)
        >>> b = Button("Ok")
        >>> clicked_buttons = []
        >>> def handle_click(button):
        ...     clicked_buttons.append(button.label)
        >>> connect_signal(b, 'click', handle_click)
        >>> b.mouse_event(size, 'mouse press', 1, 4, 0, True)
        True
        >>> b.mouse_event(size, 'mouse press', 2, 4, 0, True) # ignored
        False
        >>> clicked_buttons
        ['Ok']
        """
        if button != 1 or not is_mouse_press(event):
            return False
            
        self._emit('click')
        return True


def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()
