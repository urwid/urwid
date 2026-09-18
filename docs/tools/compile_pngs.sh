#!/bin/bash -e

# args: scripts to capture

DISPLAYNUM=5
SCREENSHOTS="$(dirname "$0")"/screenshots.sh

XVFB=$(which Xvfb)
if [ -n "$XVFB" ]; then
	Xvfb :$DISPLAYNUM -screen 0 1024x768x24 &
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
