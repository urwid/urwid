PY_INCLUDE_PATH = /usr/include/python2.4
PY_LIB = python2.4

CC = /usr/bin/gcc
CFLAGS  = -I$(PY_INCLUDE_PATH)
LDFLAGS = -l$(PY_LIB)


OFILES = str_util.o
SOFILES = $(OFILES:%.o=%.so)


all: $(SOFILES)


%.so: %.o
	$(CC) $(LDFLAGS) -shared $? -o ../urwid/$@ 


%.o: %.c
	$(CC) $(CFLAGS) -c $? -o $@	



.PHONY: clean

clean:
	rm -f  $(OFILES)
	rm -f  $(SOFILES:%=../urwid/%)