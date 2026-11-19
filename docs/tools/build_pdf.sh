#!/bin/sh
# Build the PDF documentation into build/pdf/latex/Urwid.pdf.
#
# Needs uv, LuaLaTeX and the fonts docs/conf.py names; the docs-pdf stage of .devcontainer/dev.dockerfile has them.
# Run it from the repository root, in that devcontainer or by hand:
#
#   docker build --target docs-pdf -t urwid-docs-pdf -f .devcontainer/dev.dockerfile .devcontainer
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/src" -w /src urwid-docs-pdf docs/tools/build_pdf.sh
#
# The virtual environment and the uv, TeX and fontconfig caches go under build/pdf-env in the checkout: a user passed
# with --user has no writable home directory in the image, and a fixed path in a shared /tmp could be created first by
# another user.
#
# The build fails on a Sphinx warning, and on a character that no font in the fallback chain in docs/conf.py has,
# because LuaLaTeX only logs those and draws nothing in their place.
set -eu

env_dir="$PWD/build/pdf-env"
venv="$env_dir/venv"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$env_dir/uv-cache}"
export TEXMFVAR="$env_dir/texmf-var"
export XDG_CACHE_HOME="$env_dir/cache"

uv venv --allow-existing "$venv"
VIRTUAL_ENV="$venv" uv pip install -U --group pyproject.toml:documentation
VIRTUAL_ENV="$venv" uv pip install -U -e ".[curses,glib,serial,tornado,trio,twisted,zmq]"
"$venv/bin/sphinx-build" -M latexpdf docs build/pdf -W --keep-going

if grep -A1 "Missing character" build/pdf/latex/Urwid.log; then
  echo "Characters above have no glyph in any font of the fallback chain in docs/conf.py." >&2
  exit 1
fi
