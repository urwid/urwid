#!/usr/bin/env bash -x
#
# Script to help automate the Urwid release process.

if [ -z $GITHUB_API_SECRET ]; then
    >&2 echo This script requires \$GITHUB_API_SECRET to be set for the \
        contributors module to work properly.  You can register a new token \
        at https://github.com/settings/tokens
    exit 1
fi

RELEASE=$1

RELEASE_DATE=$(date +"%Y-%m-%d")

if [ -z $RELEASE ]; then
    >&2 echo "usage: $0 x.y.z"
    exit 1
fi

PREV_RELEASE=$(grep -E "^Urwid \d+" docs/changelog.rst |
                   head -1 | cut -d' ' -f 2)
PREV_RELEASE_DATE=$(grep -E "^\d{4}-\d{2}-\d{2}" docs/changelog.rst | head -1)

echo "Bumping Urwid version from ${PREV_RELEASE} to ${RELEASE}"

read -p "Add any new maintainers to README.rst, then press return."

MAINTAINERS=($(
    awk '/Creator/,/Contributors/' README.rst |
        grep -E "^\`\S+ <//" | cut -d\` -f 2 | cut -d' ' -f 1
             ))

awk '/Contributors/,0' README.rst | grep -E "^\`\S+ <//" | cut -d\` -f 2 |
    cut -d' ' -f 1 > contributors.${PREV_RELEASE}.txt

# Build a changelog-like substance from git commit descriptions
git log --reverse --format="%s (by %an)%n" release-${PREV_RELEASE}..master |
    grep -Ev '^(Merge pull request)' | sed -e '/^$/d' | python -c '
import sys
import re

# These sections are used to sort commits based on the first word.  Anything
# not matching these keywords goes last.
sections = [
    ["Add", "Added", "Adds"],
    ["Change", "Changed", "Changes",
        "Modify", "Modified", "Modifies",
        "Update", "Updated", "Updates"],
    ["Deprecate", "Deprecated", "Deprecates"],
    ["Remove", "Removed", "Removes", "Drop", "Dropped", "Drops"],
    ["Fix", "Fixed", "Fixes"]
]


def fix_line(l):
    words = l.split()
    for s in sections:
        if any([words[0].lower() == w.lower() for w in s]):
            return " ".join([s[0]] + words[1:])
    else:
        return l

lines = [ l.strip() for l in sys.stdin.readlines() ]

# If the first line looks like a version bump to next development release,
# nuke it.
if re.search("Bump.*version.*dev", lines[0]):
    del lines[0]

lines = [
    fix_line(l)
    for l in lines
]

def sort_key(line):
    try:
        return next(
            i for i, s in enumerate(sections)
            if any([line.lower().split()[0].startswith(w.lower()) for w in s])
        )
    except StopIteration:
        return len(sections)

print("\n".join(sorted(lines, key=sort_key)))
' | sed -e "s/^/ * /" | sed G > changes.${RELEASE}.txt

perl -0777 -pe < docs/changelog.rst "
s@(Changelog\n-+)@\1

Urwid ${RELEASE}
===========

${RELEASE_DATE}

$(cat changes.${RELEASE}.txt)
@
" > docs/changelog.$RELEASE.rst

if [ $? -ne 0 ]; then
    >&2 echo "error generating changelog"
    exit 1
fi

mv docs/changelog.$RELEASE.rst docs/changelog.rst

read -p "Press return when finished verifying and cleaning up docs/changelog.rst. "

# FIXME: handle non-Github contributors?
echo "Getting contributors..."

# This script the `contributors` python module to generate a contributor listing
# from GitHub. However, there is a bug in the latest PyPi release, so we look
# for it, try it, and then install from GitHub if it doesn't work.

function install_contributors() {
    pip install -U git+https://github.com/pydanny/contributors
}

function generate_contributors() {

    contributors -f rst --since ${PREV_RELEASE_DATE} \
        -o contributors.$RELEASE.rst urwid/urwid
}

if ! command -v contributors &> /dev/null; then
    install_contributors
fi

generate_contributors

if [ $? -ne 0 ]; then
    install_contributors
    generate_contributors
fi

grep -E "^\." contributors.$RELEASE.rst \
    | cut -d@ -f 2 | cut -d\` -f 1 \
    | grep -Ev "^(invalid-email-address|ghost)$" \
    > contributors.$RELEASE.txt
        
cat contributors.$PREV_RELEASE.txt contributors.$RELEASE.txt \
    > contributors.$RELEASE.combined.txt


(
    for id in $(sort -f contributors.$RELEASE.combined.txt | uniq); do
        if [[ " ${MAINTAINERS[@]} " =~ " ${id} " ]]; then
            continue
        fi
        echo "\`${id} <//github.com/${id}>\`_,"
    done
) | sed '$ s/.$//' > contributors.${RELEASE}.rst

perl -0777 -pe < README.rst "
s@(Contributors\n-+)\n\n(?:(?!\n\n).)+@\1

$(cat contributors.${RELEASE}.rst)@ms;

" > README.${RELEASE}.rst

if [ $? -ne 0 ]; then
    >&2 echo "error updating README.rst"
    exit 1
fi

mv README.$RELEASE.rst README.rst
read -p "Press return when finished verifying and cleaning up README."

rm -f contributors.$PREV_RELEASE.* contributors.$RELEASE.* \
    changes.$RELEASE.txt

git add README.rst
git commit -m "Update README for Urwid $RELEASE"

git add docs/changelog.rst
git commit -m "Update changelog for Urwid $RELEASE"

vers=(${RELEASE//./ })
major=${vers[0]}
minor=${vers[1]}
patch=${vers[2]}

sed -i -e "s/VERSION = (.*)/VERSION = ($major, $minor, $patch)/" urwid/version.py

git add urwid/version.py
git commit -m "Bump version for Urwid ${RELEASE} release"

git tag -a release-${RELEASE} -m "Urwid ${RELEASE}"

./bin/build-pages.sh

read -p "Press return to commit doc updates, or Ctrl-C to abort."

git commit -m "Documentation updates for Urwid ${RELEASE}"

git push origin master
git push origin release-${RELEASE}
git push origin gh-pages

git checkout release-${RELEASE}

python setup.py sdist
if [ $? -ne 0 ]; then
    >&2 echo "python build failed"
    exit 1
fi

twine upload dist/urwid-${RELEASE}.tar.gz
if [ $? -ne 0 ]; then
    >&2 echo "twine upload failed"
    exit 1
fi

git checkout master
newpatch=$(( patch + 1 ))
sed -i -e "s/VERSION = (.*)/VERSION = ($major, $minor, $newpatch, 'dev')/" urwid/version.py
git add urwid/version.py
git commit -m "Bump version to ${major}.${minor}.${newpatch}-dev for development"
git push origin master
