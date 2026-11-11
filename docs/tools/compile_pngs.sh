#!/bin/bash -e

# args: scripts to capture

DISPLAYNUM=5
SCREENSHOTS="$(dirname "$0")"/screenshots.sh

XVFB=$(which Xvfb)
if [ -n "$XVFB" ]; then
	# 1600x1200 to leave headroom above the largest example window
	# (79x34 characters) rendered at the screenshot tool's 2x pixel density.
	Xvfb :$DISPLAYNUM -screen 0 1600x1200x24 &
	XVFBPID=$!
	trap 'kill "$XVFBPID"' EXIT
	export DISPLAY=:$DISPLAYNUM
	until [ -S "/tmp/.X11-unix/X${DISPLAYNUM}" ]; do sleep 0.1; done
fi

for script in "$@"; do
	echo "doing $script"
	if [ -f "${script}.xdotool" ]; then
		"$SCREENSHOTS" "$script" < "${script}.xdotool"
	fi
done
