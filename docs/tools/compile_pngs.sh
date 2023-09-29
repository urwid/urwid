#!/bin/bash -e

# args: scripts to capture

DISPLAYNUM=5
SCREENSHOTS="$(dirname "$0")"/screenshots.sh

XVFB=$(which Xvfb)
if [ -n "$XVFB" ]; then
	Xvfb :$DISPLAYNUM -screen 0 1024x768x24 &
	XVFBPID=$!
	echo "[ ] launched Xvfb $XVFBPID"
	until test -S /tmp/.X11-unix/X${DISPLAYNUM}; do sleep 0.1; done; sleep 0.2
	trap 'echo "[ ] killing Xvfb $XVFBPID"; kill -INT $XVFBPID; wait $XVFBPID' EXIT
	export DISPLAY=:$DISPLAYNUM
	export XVFBPID
fi

for script in "$@"; do
	if [ -f "${script}.xdotool" ]; then
		echo
		echo "doing $script"
		timeout 60 "$SCREENSHOTS" "$script" < "${script}.xdotool"
	fi
done
