#!/bin/bash

# $1: python script to run
# urxvt, xdotool and import are required to run this script

CLASSNAME=$(head -c 6 /dev/urandom | base64 | tr -cd '[:alnum:]')
PYTHON=${PYTHON:-python}

urxvt -bg gray90 -b 0 +sb \
	-fn 'xft:DejaVu Sans Mono:pixelsize=13' \
	-fb 'xft:DejaVu Sans Mono:pixelsize=13:style=Bold' \
	-name "$CLASSNAME" -e "$PYTHON" "$1" &
RXVTPID=$!
trap 'kill "$RXVTPID" 2>/dev/null' EXIT

RXVTWINDOWID=$(xdotool search --sync --classname "$CLASSNAME")
export RXVTWINDOWID
image=${1%.py}

# Wait until the example (and any process it spawned, e.g. a subprocess
# example) has stopped actively computing/redrawing: poll /proc for a
# running (R) state, and consider things settled once none of the tracked
# processes have been running for a few consecutive polls. This is more
# reliable than a fixed sleep, since examples like the directory browser
# can take a variable amount of time to build their initial listing.
wait_example_settled() {
	local -i idle_polls=0
	local -i poll=0
	while (( poll < 200 )); do
		local -i running=0
		local pid
		for pid in "$RXVTPID" $(pgrep -P "$RXVTPID") $(pgrep -g "$RXVTPID" 2>/dev/null); do
			[ -r "/proc/$pid/stat" ] || continue
			read -r _ _ state _ < "/proc/$pid/stat"
			[ "$state" = "R" ] && running=1
		done
		if [ "$running" -eq 1 ]; then
			idle_polls=0
		else
			(( ++idle_polls ))
			(( idle_polls >= 3 )) && return
		fi
		sleep 0.05
		(( ++poll ))
	done
}

# Give urxvt a moment to finish its own startup redraw before the first
# keystroke lands, otherwise the first screenshot can be taken mid-repaint.
wait_example_settled

counter=1
while read -r line; do
	# the echo trick is needed to expand RXVTWINDOWID variable
	echo $line | xdotool -
	echo "sending $line"
	wait_example_settled
	import -window "$RXVTWINDOWID" "${image}$counter.png"
	(( counter++ ))
done

kill "$RXVTPID" 2>/dev/null
