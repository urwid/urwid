
PYTHON_SOURCE=$(shell echo */*.py.xdotool)
TARGETS=${PYTHON_SOURCE:.py.xdotool=1.png}
TOOLS=tools/compile_pngs.sh tools/screenshots.sh
EXTERNAL_PROGRAMS=Xvfb xterm xdotool import

.PHONY: all clean ${EXTERNAL_PROGRAMS}

all: ${TARGETS}

${TARGETS}: %1.png: %.py %.py.xdotool ${TOOLS} ${EXTERNAL_PROGRAMS}
	tools/compile_pngs.sh $<

${EXTERNAL_PROGRAMS}:
	@which $@ > /dev/null || (echo "Need to install $@"; exit 1)

apt-get-dependencies:
	sudo apt-get install xvfb xterm xdotool imagemagick fonts-dejavu-core

clean:
	rm -f ${TARGETS}
