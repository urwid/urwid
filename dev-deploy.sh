#!/bin/bash
if [ -z "$1" ]; then
   echo "Usage: $0 <hostname> " 1>&2
   exit 1
fi
HOST=$1
# if host does not contain "<user>@" then prefix with root@ (since it's likely a krusty cluster)
if [[ ! $HOST == *"@"* ]]; then
    HOST="root@$HOST"
fi
shift
THISDIR=$(dirname "$(readlink -f "$0")")
TARGET_PKG_DIR=$HOST:/cm/local/apps/cm-setup/lib/python3.12/site-packages
EXCLUDE="--exclude=Makefile"
rsync --filter=':- .gitignore' "$@" -avz $EXCLUDE $THISDIR/urwid/ $TARGET_PKG_DIR/urwid/
