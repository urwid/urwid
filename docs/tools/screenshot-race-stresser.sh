#!/bin/bash

cd "$(dirname "$0")"/.. || die

rm -rf examples.ref; mkdir -vp examples.ref; cp -v examples/*.png examples.ref

counter=1
until [[ $counter -eq 100 ]]; do

    echo
    echo
    echo "================================================================================"
    echo "===           iteration $counter"
    echo "================================================================================"
    tools/compile_pngs.sh examples/*.py

    for r in examples.ref/*.png; do
        n=$(basename $r)
        t=examples/$n
        d=/tmp/diff-$n
        #-- use compare from ImageMagick
        if ! compare $r $t $d; then
            echo "changes detected, aborting stresstest! see $d"
            exit 1
        fi
    done

    : $((++counter))
done

exit 0
