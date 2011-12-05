#!/bin/bash -e

# $1: directory to compile
DISPLAYNUM=1

XVFB=$(which Xvfb)
if [ -n $XVFB ]; then
	# Xvfb :$DISPLAYNUM &> /dev/null &
	Xvfb :$DISPLAYNUM &
	XVFBPID=$!
	# DISPLAY=:1
	sleep 0.5
	trap "kill $XVFBPID" EXIT
fi

for script in $1/*.py; do
	if [ -f "${script}.xdotool" ]; then
		bash screenshots.sh "$script" < "${script}.xdotool"
	fi
done
