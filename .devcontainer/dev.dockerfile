FROM python:3.12
RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get install -y python3-gi gobject-introspection libgirepository1.0-dev \
    && apt-get clean
RUN mkdir -p ~/.virtualenvs \
    && pip3 install virtualenv \
    && /usr/local/bin/virtualenv -p /usr/local/bin/python3 --download ~/.virtualenvs/urwid