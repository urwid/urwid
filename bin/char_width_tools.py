#!/usr/bin/env python

# Build a table of unicode character widths as rendered by the current terminal.

import sys
import tty
import termios
from select import select
import re
import argparse
import csv

MIN_CODE_POINT = 0
MAX_CODE_POINT = 0x110000

ESC = "\x1b"
CLEAR = ESC + "[2J"

BEGINNING_OF_LINE = ESC +"[1;2H"

def getpos():

    buf = ""
    stdin = sys.stdin.fileno()
    tattr = termios.tcgetattr(stdin)

    try:
        tty.setcbreak(stdin, termios.TCSANOW)
        sys.stdout.write("\x1b[6n")
        sys.stdout.flush()

        while True:
            buf += sys.stdin.read(1)
            if buf[-1] == "R":
                break

    finally:
        termios.tcsetattr(stdin, termios.TCSANOW, tattr)

    return [
        int(x)
        for x in re.match(r"^\x1b\[(\d*);(\d*)R", buf).groups()
    ]


def get_width(i):
    c = chr(i)
    print(BEGINNING_OF_LINE)
    try:
        sys.stdout.write(c)
    except UnicodeEncodeError:
        return None
    return getpos()[1]-1


def test_string(s):

    widths = []
    for c in s:
        widths.append(get_width(ord(c)))

    print(CLEAR)

    for c, w in zip(s, widths):
        print("%s\t%d" %(c, w))
    print()
    print("total\t%d" %(sum(widths)))

def write_table(filename):
    widths = list()
    last_width = None

    try:
        for i in range(MIN_CODE_POINT, MAX_CODE_POINT):
            w = get_width(i)
            if w is None:
                continue
            if i != MIN_CODE_POINT and w != last_width:
                widths.append((i-1, last_width))
            last_width = w
            if not i % 1000:
                pct = i / MAX_CODE_POINT
                print()
                print("%d/%d (%.02f%%)" %(i, MAX_CODE_POINT, pct*100))
        widths.append((i, last_width))

    finally:
        with open(filename, "w") as f:
            writer = csv.writer(f)
            for w in widths:
                writer.writerow("%d\t%d\n" %(w[0], w[1]))


def dump(infile, lang):

    widths = list()
    last_width = None

    with open(infile) as f:
        reader = csv.reader(f)
        for row in reader:
            widths.append((row[0], row[1]))

    if args.lang == "c":
        print("static const int widths[] = {")
    elif args.lang == "python":
        print("widths = [")

    for i, w in widths:
        if lang == "c":
            print("    %s, %s," %(i, w))

        elif lang == "python":
            print("    (%s, %s)," %(i, w))
        else:
            raise RuntimeError("unknown language")

    if lang == "c":
        print("    NULL")
        print("};")
    elif lang == "python":
        print("]")

def main():

    global args
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze character widths and save them to csv file"
    )
    analyze_parser.add_argument(
        "outfile", metavar="FILE",
        help="write character widths to this file"
    )
    analyze_parser.set_defaults(func=lambda args: write_table(args.outfile))

    test_parser = subparsers.add_parser(
        "test",
        help="analyze a set of characters specified on the command line"
    )
    test_parser.add_argument(
        "string", metavar="CHAR",
        help="character to test"
    )
    test_parser.set_defaults(func=lambda args: test_string(args.string))

    dump_parser = subparsers.add_parser(
        "dump",
        help="generate source code for width tables from a saved file"
    )
    dump_parser.add_argument(
        "infile", metavar="FILE",
        help="read character widths from this file"
    )
    dump_parser.add_argument(
        "lang", metavar="LANGUAGE", choices=["c", "python"],
        help="Language to dump data for."
    )
    dump_parser.set_defaults(func=lambda args: dump(args.infile, args.lang))

    args = parser.parse_args()

    print(CLEAR)

    args.func(args)

if __name__ == "__main__":
    main()
