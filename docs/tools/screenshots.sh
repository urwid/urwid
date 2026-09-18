#!/bin/bash

# $1: python script to run
# urxvt, xdotool and import are required to run this script

CLASSNAME=$(head -c 6 /dev/urandom | base64 | tr -cd '[:alnum:]')
PYTHON=${PYTHON:-python}

# Rendered at 2x the logical pixel size (26, twice the 13px logical size)
# with antialiasing off, so the resulting PNGs are sharp on HiDPI displays;
# the docs' ``:scale: 50%`` on each image directive shows them at the
# original logical size everywhere else. Downscaling this 2x capture is
# also what keeps text looking clean rather than jagged at logical size:
# the extra samples get averaged away in the process instead of being
# thrown away, unlike rendering directly at 1x without antialiasing.
#
# We tried Terminus, a font with hand-drawn bitmap strikes at fixed pixel
# sizes, since unlike a scaled vector font (e.g. DejaVu Sans Mono) it stays
# crisp and symmetric at a given size instead of producing uneven,
# "dancing" glyphs. But at 2x pixel size, several non-Latin fallback
# glyphs (used by edit.py's Unicode showcase: Georgian, math symbols, some
# CJK) rendered as missing-glyph boxes instead of falling back the way
# they do at 1x -- so we stayed on DejaVu Sans Mono, which has full
# coverage for everything the examples use, and rely on the 2x-then-
# downscale trick above for crispness instead.
urxvt -bg gray90 -b 0 +sb \
	-fn 'xft:DejaVu Sans Mono:pixelsize=26:antialias=false' \
	-fb 'xft:DejaVu Sans Mono:pixelsize=26:style=Bold:antialias=false' \
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
