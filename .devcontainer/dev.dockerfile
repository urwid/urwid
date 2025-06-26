FROM ubuntu:24.04
RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get install -y \
      python3-dev \
      python3-pip \
      python3-virtualenv \
      python3-gi \
      python3-gi-cairo \
      gobject-introspection \
      libgirepository-2.0-dev \
      libcairo2-dev \
    && apt-get clean
RUN mkdir -p ~/.virtualenvs \
    && virtualenv --download ~/.virtualenvs/urwid
