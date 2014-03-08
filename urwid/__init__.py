#!/usr/bin/python
#
# Urwid __init__.py - all the stuff you're likely to care about
#
#    Copyright (C) 2004-2012  Ian Ward
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

import sys

class _UrwidModule(object):
    """
    Import specific names from deeper in the urwid module hierarchy
    to the top level because urwid was once a small library with
    everything in one module, and life is easier for users this way.

    This class lazily imports so all users don't need to pay the
    price of importing almost all urwid sub-modules on startup.
    """
    from urwid.version import VERSION, __version__

    _names = {
        'widget': (
            'FLOW', 'BOX', 'FIXED', 'LEFT', 'RIGHT', 'CENTER', 'TOP', 'MIDDLE',
            'BOTTOM', 'SPACE', 'ANY', 'CLIP', 'PACK', 'GIVEN', 'RELATIVE',
            'RELATIVE_100', 'WEIGHT', 'WidgetMeta',
            'WidgetError', 'Widget', 'FlowWidget', 'BoxWidget', 'fixed_size',
            'FixedWidget', 'Divider', 'SolidFill', 'TextError', 'Text',
            'EditError', 'Edit', 'IntEdit', 'delegate_to_widget_mixin',
            'WidgetWrapError', 'WidgetWrap'),
        'decoration': (
            'WidgetDecoration', 'WidgetPlaceholder',
            'AttrMapError', 'AttrMap', 'AttrWrap', 'BoxAdapterError',
            'BoxAdapter', 'PaddingError',
            'Padding', 'FillerError', 'Filler', 'WidgetDisable'),
        'container': (
            'GridFlowError', 'GridFlow', 'OverlayError', 'Overlay',
            'FrameError', 'Frame', 'PileError', 'Pile', 'ColumnsError',
            'Columns', 'WidgetContainerMixin'),
        'wimp': (
            'SelectableIcon', 'CheckBoxError', 'CheckBox', 'RadioButton',
            'Button', 'PopUpLauncher', 'PopUpTarget'),
        'listbox': (
            'ListWalkerError', 'ListWalker', 'PollingListWalker',
            'SimpleListWalker', 'SimpleFocusListWalker', 'ListBoxError',
            'ListBox'),
        'graphics': (
            'BigText', 'LineBox', 'BarGraphMeta', 'BarGraphError',
            'BarGraph', 'GraphVScale', 'ProgressBar', 'scale_bar_values'),
        'canvas': (
            'CanvasCache', 'CanvasError', 'Canvas', 'TextCanvas',
            'BlankCanvas', 'SolidCanvas', 'CompositeCanvas', 'CanvasCombine',
            'CanvasOverlay', 'CanvasJoin'),
        'font': (
            'get_all_fonts', 'Font', 'Thin3x3Font', 'Thin4x3Font',
            'HalfBlock5x4Font', 'HalfBlock6x5Font', 'HalfBlockHeavy6x5Font',
            'Thin6x6Font', 'HalfBlock7x7Font'),
        'signals': (
            'MetaSignals', 'Signals', 'emit_signal', 'register_signal',
            'connect_signal', 'disconnect_signal'),
        'monitored_list': (
            'MonitoredList', 'MonitoredFocusList'),
        'command_map': (
            'CommandMap', 'command_map',
            'REDRAW_SCREEN', 'CURSOR_UP', 'CURSOR_DOWN', 'CURSOR_LEFT',
            'CURSOR_RIGHT', 'CURSOR_PAGE_UP', 'CURSOR_PAGE_DOWN',
            'CURSOR_MAX_LEFT', 'CURSOR_MAX_RIGHT', 'ACTIVATE'),
        'main_loop': (
            'ExitMainLoop', 'MainLoop', 'SelectEventLoop',
            'TwistedEventLoop', 'GLibEventLoop', 'TornadoEventLoop'),
        'text_layout': (
            'TextLayout', 'StandardTextLayout', 'default_layout',
            'LayoutSegment'),
        'display_common': (
            'UPDATE_PALETTE_ENTRY', 'DEFAULT', 'BLACK',
            'DARK_RED', 'DARK_GREEN', 'BROWN', 'DARK_BLUE', 'DARK_MAGENTA',
            'DARK_CYAN', 'LIGHT_GRAY', 'DARK_GRAY', 'LIGHT_RED', 'LIGHT_GREEN',
            'YELLOW', 'LIGHT_BLUE', 'LIGHT_MAGENTA', 'LIGHT_CYAN', 'WHITE',
            'AttrSpecError', 'AttrSpec', 'RealTerminal',
            'ScreenError', 'BaseScreen'),
        'util': (
            'calc_text_pos', 'calc_width', 'is_wide_char',
            'move_next_char', 'move_prev_char', 'within_double_byte',
            'detected_encoding', 'set_encoding', 'get_encoding_mode',
            'apply_target_encoding', 'supports_unicode',
            'calc_trim_text', 'TagMarkupException', 'decompose_tagmarkup',
            'MetaSuper', 'int_scale', 'is_mouse_event'),
        'treetools': (
            'TreeWidgetError', 'TreeWidget', 'TreeNode',
            'ParentNode', 'TreeWalker', 'TreeListBox'),
        'vterm': (
            'TermModes', 'TermCharset', 'TermScroller', 'TermCanvas',
            'Terminal'),
        'raw_display': (),
        }

    _reverse_names = dict((name, mod) for mod, names in _names.iteritems()
        for name in names)

    # allow imports of sub-modules to continue to work properly
    __path__ = __path__

    # 3.3 compat
    __name__ = __name__

    def __getattr__(self, name):
        """
        Lazy import machinery. Use normal import statements to make
        it easier for things like pyinstaller to tell what modules
        get imported.
        """
        found = self._reverse_names.get(name)
        if not found:
            if name in self._names:
                found = name
            else:
                raise AttributeError("urwid has no attribute '%s'" % name)
        if found == 'widget':
            import urwid.widget
        elif found == 'decoration':
            import urwid.decoration
        elif found == 'container':
            import urwid.container
        elif found == 'wimp':
            import urwid.wimp
        elif found == 'listbox':
            import urwid.listbox
        elif found == 'graphics':
            import urwid.graphics
        elif found == 'canvas':
            import urwid.canvas
        elif found == 'font':
            import urwid.font
        elif found == 'signals':
            import urwid.signals
        elif found == 'monitored_list':
            import urwid.monitored_list
        elif found == 'command_map':
            import urwid.command_map
        elif found == 'main_loop':
            import urwid.main_loop
        elif found == 'text_layout':
            import urwid.text_layout
        elif found == 'display_common':
            import urwid.display_common
        elif found == 'util':
            import urwid.util
        elif found == 'treetols':
            import urwid.treetols
        elif found == 'vterm':
            import urwid.vterm
        elif found == 'raw_display':
            import urwid.raw_display
        else:
            assert 0, 'missing import line for %s' % found

        if found:
            module = getattr(urwid, found)
            for n in self._names[found]:
                setattr(self, n, getattr(module, n))
            setattr(self, found, module)

        return getattr(self, name)


# https://mail.python.org/pipermail/python-ideas/2012-May/014969.html
sys.modules[__name__] = _UrwidModule()
