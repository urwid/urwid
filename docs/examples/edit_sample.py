"""Count the words of a file."""

import sys


def count_words(path):
    """Return the number of words in the file *path*."""
    with open(path, encoding="utf-8") as stream:
        return sum(len(line.split()) for line in stream)  # per line


if __name__ == "__main__":
    print(count_words(sys.argv[1]), "words")
