#!/bin/bash

# $1: python script to run
# xterm, xdotool and import are required to run this script

CLASSNAME=$(head -c 6 /dev/urandom | base64 | tr -cd '[:alnum:]')
PYTHON=${PYTHON:-python}

# 2x size for HiDPI; docs' ``:scale: 50%`` shows them at logical size.
#
# Font            | Rejected because
# ----------------|--------------------------------------------------
# DejaVu 1x       | uneven/"dancing" glyphs (e.g. "8"); fixed by 2x above
# Terminus 2x     | breaks Unicode fallback (tofu for Georgian/math/CJK)
# Cascadia Mono   | shade blocks (U+2591-2593) render as a diagonal weave
# Liberation Mono | rounded box corners (U+256D-2570) don't meet the lines
# DejaVu 2x       | chosen; only con is 1/l/I and 0/O are hard to tell apart
#
# Terminal | Rejected because
# ---------|----------------------------------------------------
# urxvt    | no color-glyph support -> emoji always render as tofu
# xterm    | chosen; needs allowSendEvents below or it silently
#          | discards the synthetic keys xdotool sends us
#
# -tn: xterm's own TERM default is plain "xterm", not 256-color.
xterm -bg gray90 -fg black -b 0 +sb -tn xterm-256color \
	-fa 'DejaVu Sans Mono:pixelsize=26:antialias=false' \
	-xrm 'XTerm*allowSendEvents: true' \
	-name "$CLASSNAME" -e "$PYTHON" "$1" &
TERMPID=$!
trap 'kill "$TERMPID" 2>/dev/null' EXIT

TERMWINDOWID=$(xdotool search --sync --classname "$CLASSNAME")
export TERMWINDOWID
image=${1%.py}

# More reliable than a fixed sleep: some examples (e.g. the directory
# browser) take a variable amount of time to settle.
wait_example_settled() {
	local -i idle_polls=0
	local -i poll=0
	while (( poll < 200 )); do
		local -i running=0
		local pid
		for pid in "$TERMPID" $(pgrep -P "$TERMPID") $(pgrep -g "$TERMPID" 2>/dev/null); do
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

# let xterm finish its startup redraw before the first keystroke
wait_example_settled

counter=1
while read -r line; do
	# the echo trick is needed to expand TERMWINDOWID variable
	echo $line | xdotool -
	echo "sending $line"
	wait_example_settled
	import -window "$TERMWINDOWID" "${image}$counter.png"
	# 192 DPI (2x baseline); exclude-chunk drops mogrify's own tIME/date
	# stamps, which would otherwise make reruns produce different bytes.
	mogrify -units PixelsPerInch -density 192 -define png:exclude-chunk=date,time "${image}$counter.png"
	(( counter++ ))
done

kill "$TERMPID" 2>/dev/null
