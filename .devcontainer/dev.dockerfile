FROM ubuntu:26.04 AS dev
RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get install -y \
      python3-dev \
      python3-gi \
      python3-gi-cairo \
      gobject-introspection \
      libgirepository-2.0-dev \
      libcairo2-dev \
      curl \
      sudo \
      xvfb \
      xterm \
      xdotool \
      imagemagick \
      fonts-dejavu-core \
      fonts-noto-core \
      fonts-noto-cjk \
      fonts-noto-color-emoji \
    && apt-get clean

# Install uv globally to /usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# Set uv to use temporary venv location outside workspace
ENV UV_PROJECT_ENVIRONMENT=/home/ubuntu/.venv-urwid

# Without this, the container's only locale is the non-UTF-8 "C", which
# breaks docs/tools/screenshots.sh: xterm mis-decodes the multi-byte
# UTF-8 the doc examples display (CJK, Georgian, box-drawing, emoji).
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Xvfb (used by docs/tools/compile_pngs.sh) needs this directory to
# exist with these permissions before it can create its socket; a
# non-root container user can't create it itself.
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# The PDF documentation, built by docs/tools/build_pdf.sh: LuaLaTeX, latexmk
# and the LaTeX packages Sphinx uses, with FreeFont for the text. The fonts
# installed above are the fallbacks docs/conf.py names for the box-drawing,
# CJK, emoji and symbol characters. xindy builds the index for LuaLaTeX.
# .github/workflows/documentation-pdf.yml installs the same packages; a
# change to one list is made to the other.
FROM dev AS docs-pdf
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
      latexmk \
      texlive-luatex \
      texlive-latex-recommended \
      texlive-latex-extra \
      texlive-fonts-recommended \
      xindy \
      fonts-freefont-otf \
    && apt-get clean
