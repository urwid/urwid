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
    && apt-get clean

# Install uv globally to /usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# Set uv to use temporary venv location outside workspace
ENV UV_PROJECT_ENVIRONMENT=/home/ubuntu/.venv-urwid
