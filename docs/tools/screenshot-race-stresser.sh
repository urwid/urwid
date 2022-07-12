#!/bin/bash

cd "$(dirname "$0")"/.. || die

counter=100
until [[ $counter -eq 0 ]]; do

    echo
    echo
    echo "================================================================================"
    echo "===           iteration $counter"
    echo "================================================================================"
    tools/compile_pngs.sh examples/*.py

    if ! git diff --quiet ./\*\*.png; then
        git status
        echo "changes detected, aborting stresstest!"
        exit 1
    fi

    : $((--counter))
done

exit 0
