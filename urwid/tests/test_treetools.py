# -*- coding: utf-8 -*-
import unittest
from textwrap import dedent

from urwid.compat import B
import urwid


class ExampleTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    def get_display_text(self):
        return self.get_node().get_value()['name']


class ExampleNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return ExampleTreeWidget(self)


class ExampleParentNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes """
    def load_widget(self):
        return ExampleTreeWidget(self)

    def load_child_keys(self):
        data = self.get_value()
        return range(len(data['children']))

    def load_child_node(self, key):
        """Return either an ExampleNode or ExampleParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = ExampleParentNode
        else:
            childclass = ExampleNode
        return childclass(childdata, parent=self, key=key, depth=childdepth)


class TreeToolsTest(unittest.TestCase):
    def setUp(self):
        self.data = dict(
            name='Countries',
            children=[
                dict(
                    name='Ukraine',
                    children=[
                        dict(
                            name='Lviv'
                        ),
                        dict(
                            name='Kyiv'
                        )
                    ]
                ),
                dict(
                    name='United States of America',
                    children=[
                        dict(
                            name='New York'
                        ),
                        dict(
                            name='Los Angeles'
                        )
                    ]
                )
            ]
        )
        self.node = ExampleParentNode(self.data)
        # self.tree = ExampleTreeWidget(self.node)
        # self.tree.expanded = True
        self.listbox = urwid.TreeListBox(urwid.TreeWalker(self.node))

        self.expected_tree = dedent('''\
            - Countries
               - Ukraine
                  Lviv
                  Kyiv
               - United States of America
                  New York
                  Los Angeles
        ''')

    def test_render_listbox(self):
        canvas = self.listbox.render((30, 8))
        lines = [
            ''.join([
                (block[2] if isinstance(block, tuple) else block).decode('utf-8')
                for block
                in line
            ]).rstrip()
            for line
            in canvas.content()
        ]
        result = '\n'.join(lines)
        self.assertEqual(result, self.expected_tree)

