#!/bin/bash -e

# $1: directory to compile
# $2: compiler

DISPLAYNUM=1

XVFB=$(which Xvfb)
if [ -n $XVFB ]; then
	Xvfb :$DISPLAYNUM &
	XVFBPID=$!
	DISPLAY=:$DISPLAYNUM # this still doesn't work
	trap "kill $XVFBPID" EXIT
fi

for script in $1/*.py; do
	if [ -f "${script}.xdotool" ]; then
		"$2" "$script" < "${script}.xdotool"
	fi
done
