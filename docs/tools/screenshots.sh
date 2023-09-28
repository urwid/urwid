#!/bin/bash

# $1: python script to run
# urxvt, xdotool and import are required to run this script

CLASSNAME=urwid-docs-$(head -c 6 /dev/urandom | base64 | tr -cd '[:alnum:]')
PYTHON=python

urxvt -bg gray90 -b 0 +sb \
	-fn 'xft:Monospace:pixelsize=20' \
	-fb 'xft:Monospace-Bold:pixelsize=20' \
	-name "$CLASSNAME" \
	-e "$PYTHON" "$1" &
RXVTPID=$!
trap 'kill $RXVTPID' EXIT
until RXVTWINDOWID=$(xdotool search --classname "$CLASSNAME"); do
	sleep 0.1
done
export RXVTWINDOWID
image=${1%.py}

# Synchronize to a point when the example has finished rendering.
# Once in n consecutive polls we don't see any "R (running)", consider that the
# process has completed the initial rendering & processing xdotool events,
# and has become idle.
# With increasing n, the probability of misdetection falls exponentially.
sync_example_settled() {
	pid=$1
	n=0
	while (( n < 80 )); do
		sleep 0.005
		procstate="$(cut -d' ' -f3 < /proc/"$pid"/stat)"
		case $procstate in
			R) n=0; printf '!';;
			*) _=$(( ++n )); printf '.';;
		esac
	done
	echo
}

# target script is interpreted by python, use its PID
example_pid="$(pgrep -P $RXVTPID python)"

c=1
while read -r line; do
	# the echo trick is needed to expand RXVTWINDOWID variable
	echo $line | xdotool - 2>/dev/null
	echo "sending $line"
	sync_example_settled "$example_pid"
	import -window "$RXVTWINDOWID" "${image}$c.png"
	(( c++ ))
done
