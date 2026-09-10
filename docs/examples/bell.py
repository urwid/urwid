#!/usr/bin/env python
"""
Urwid example: Terminal Bell (Beep)
Demonstrates how to trigger a terminal bell sound using the ASCII BEL character.
"""

import urwid

def exit_on_q(key):
    """Press 'q' to exit the program."""
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

def make_beep(key):
    """
    Trigger a terminal bell.
    In many terminals, printing '\a' triggers the system bell or visual bell.
    """
    # urwid.Text widget content update is not enough to trigger sound usually,
    # we need to write to stdout or use the terminal's capability.
    # However, in a raw terminal mode managed by urwid, simply printing 
    # might be intercepted. 
    
    # The most reliable way in a curses/raw terminal environment is often
    # writing directly to the file descriptor or relying on the terminal 
    # to interpret the output stream.
    
    # For this simple example, we will try to print to stdout. 
    # Note: Depending on how urwid manages stdout, this might need 
    # specific handling, but let's try the standard approach first.
    
    # Actually, writing to sys.stdout inside the main loop might mess up urwid's screen.
    # A safer way for a "demo" that doesn't break the screen is using 
    # os.write(1, b'\a') which writes directly to fd 1 (stdout).
    import os
    os.write(1, b'\a') 

def main():
    # Create a simple text widget
    txt = urwid.Text(
        "Press [B] to ring the terminal bell.\n"
        "Press [Q] to quit.",
        align='center'
    )
    
    # Wrap it in a Pile or just use it directly with padding
    fill = urwid.Filler(txt, 'middle')
    
    # Setup input handling
    def input_handler(key):
        if key == 'b':
            make_beep(key)
            txt.set_text("Bell rang! (Did you hear it?)\nPress [B] again or [Q] to quit.")
        elif key == 'q':
            raise urwid.ExitMainLoop()
            
    loop = urwid.MainLoop(fill, unhandled_input=input_handler)
    loop.run()

if __name__ == '__main__':
    main()