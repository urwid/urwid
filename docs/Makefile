
PYTHON_SOURCE=$(shell echo */*.py.xdotool)
TARGETS=${PYTHON_SOURCE:.py.xdotool=1.png}
TOOLS=tools/compile_pngs.sh tools/screenshots.sh

.PHONY: all

all: ${TARGETS}

${TARGETS}: %1.png: %.py %.py.xdotool ${TOOLS}
	echo zzz $<
	tools/compile_pngs.sh $<

apt-get-dependencies:
	sudo apt-get install xvfb rxvt-unicode-256color xdotool
