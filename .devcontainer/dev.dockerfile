FROM ubuntu:26.04
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
