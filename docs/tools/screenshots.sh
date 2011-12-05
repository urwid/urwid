#!/bin/bash

# $1: python script to run
# urxvt, xdotool and import are required to run this script

# this should be pretty unique, but a true random classname is still possible
# CLASSNAME=$(head -c 6 /dev/urandom | base64)
CLASSNAME=urwid-screenshot
PYTHON=python

urxvt -bg gray90 -b 0 +sb -name "$CLASSNAME" -e "$PYTHON" "$1" &
RXVTPID=$!
sleep 0.2
RXVTWINDOWID=$(xdotool search --classname "$CLASSNAME")
export RXVTWINDOWID
image=${1%.py}

c=1
while read -r line; do
	# the echo trick is needed to expand RXVTWINDOWID variable
	echo $line | xdotool -
	import -window "$RXVTWINDOWID" "${image}$c.png"
	(( c++ ))
done

kill $RXVTPID
