import urwid

def menu_button(caption, callback, data=None):
    button = urwid.Button(caption)
    urwid.connect_signal(button, 'click', callback, data)
    return urwid.AttrMap(button, None, focus_map='reversed')

def sub_menu(caption, choices):
    contents = menu(caption, choices)
    return menu_button(u'MENU: %s' % caption, open_menu, contents)

def menu(title, choices):
    body = [urwid.Text(title), urwid.Divider()]
    body.extend(choices)
    return urwid.ListBox(urwid.SimpleListWalker(body))

def open_menu(button, menu):
    loop.widget = menu

def item_chosen(button):
    response = urwid.Text(u'You chose %s' % button.label)
    loop.widget = urwid.Filler(response)
    # exit on the next input from user
    loop.unhandled_input = exit_program

def exit_program(key):
    raise urwid.ExitMainLoop()

menu_top = menu(u'Main Menu', [
    sub_menu(u'Applications', [
        sub_menu(u'Accessories', [
            menu_button(u'Text Editor', item_chosen),
            menu_button(u'Terminal', item_chosen),
        ]),
    ]),
    sub_menu(u'System', [
        sub_menu(u'Preferences', [
            menu_button(u'Appearance', item_chosen),
        ]),
        menu_button(u'Lock Screen', item_chosen),
    ]),
])

loop = urwid.MainLoop(menu_top,
    palette=[('reversed', 'standout', '')])
loop.run()
