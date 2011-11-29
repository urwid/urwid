#!/bin/sh

set -e

python docgen_tutorial.py -H > ../tutorial.html
python docgen_tutorial.py -s
mkdir -p ../tutorial_examples
ln -s ../../urwid ../tutorial_examples/urwid
mv example*py ../tutorial_examples/

python docgen_reference.py > ../reference.html
