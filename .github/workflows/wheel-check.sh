#!/usr/bin/env bash

set -euxo pipefail

EXPECTED_WHEEL_COUNT=$1

if ! [ -n $EXPECTED_WHEEL_COUNT ]; then
    exit 0
fi

WHEELS=$(find . -maxdepth 3 -name \*.whl)
if [ $(echo $WHEELS | wc -w) -ne $EXPECTED_WHEEL_COUNT ]; then
    echo "Error: Expected $EXPECTED_WHEEL_COUNT wheels"
    exit 1
else
    exit 0
fi
