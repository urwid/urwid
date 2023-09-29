#!/bin/bash

# $1: python script to run
# urxvt, xdotool, ImageMagick are required to run this script

CLASSNAME=urwid-docs-$(head -c 6 /dev/urandom | base64 | tr -cd '[:alnum:]')
PYTHON=python

image=${1%.py}

# For synchronization, we'll poll process status (running or not) of the
# terminal emulator, python interpreter, and any processes spawned by it
# (like e.g. in the subproc example).
urxvt -bg gray90 -b 0 +sb \
	-fn 'xft:DejaVu Sans Mono:pixelsize=20' \
	-fb 'xft:DejaVu Sans Mono:pixelsize=20:style=Bold' \
	-name "$CLASSNAME" \
	-e "$PYTHON" "$1" &
RXVTPID=$!
export RXVTPID
trap 'kill $RXVTPID' EXIT

# sync to urxvt starting and creating a window
until RXVTWINDOWID=$(xdotool search --classname "$CLASSNAME"); do
	sleep 0.1
done
export RXVTWINDOWID

# Some examples spawn subprocesses. We want to poll those, too
PYCHILD="$(pgrep --parent $RXVTPID python)"
list_example_processes() { pgrep -g $PYCHILD; }

# Synchronize to a point when the example has finished rendering.
# Once in n consecutive polls we don't see any "R (running)", consider that the
# processes have finished:
#  * computing and output of terminal escape sequences (urwid -> urxvt),
#  * repaints into the virtual framebuffer (urxvt -> Xvfb),
#  * injected X11 event handling (xdotool -> Xvfb -> urxvt -> urwid),
# and have become idle.
# With increasing n, the probability of misdetection falls exponentially.
sync_example_settled() {
	declare -a pids=("$@")
	declare -a chars=( A B C D E F G ) #-- add more as needed
	set -u
	local -i n
	n=0
	while (( n < 80 )); do
		sleep 0.005
		local -i nrunning=0
		for i in "${!pids[@]}"; do
			pid=${pids[i]}
			procstate="$(cut -d' ' -f3 < /proc/"$pid"/stat)"
			case $procstate in
				R) : $(( ++nrunning )); printf %c "${chars[i]}";;
				*) ;;
			esac
		done
		if (( nrunning > 0 )); then
			n=0
		else
			printf .
			: $(( ++n ))
		fi
	done
	echo
}

c=1
while read -r line; do
	# the echo trick is needed to expand RXVTWINDOWID variable
	echo $line | xdotool - 2>/dev/null
	echo "sending $line"
	sync_example_settled "$XVFBPID" "$RXVTPID" $(list_example_processes)
	import -window "$RXVTWINDOWID" "${image}$c.png"
	(( c++ ))
done
