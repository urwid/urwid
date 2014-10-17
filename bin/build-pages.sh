#!/bin/bash

set -e

cd "`dirname $0`/.."
rm -r build/sphinx || true
python setup.py build_sphinx

git checkout gh-pages
git fetch origin gh-pages
git merge --ff-only origin/gh-pages
git rm `git ls-files`
git checkout HEAD CNAME
git checkout HEAD .nojekyll
cp -r build/sphinx/html/. .
git add `find build/sphinx/html | cut -c 19-`
git status
