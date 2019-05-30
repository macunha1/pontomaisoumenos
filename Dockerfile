FROM python:3.6.7-slim-jessie

ARG TIMEZONE

# Reducing the quantity of image layers through less commands
RUN printf 'deb http://archive.debian.org/debian/ jessie main \n\
    deb-src http://archive.debian.org/debian/ jessie main \n\
    deb http://security.debian.org jessie/updates main \n\
    deb-src http://security.debian.org jessie/updates main' \
        > /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends apt-utils && \
    # Install Dependencies
    apt-get install build-essential -qq \
        libpq-dev && \
    [ -e /etc/localtime ] && rm -f /etc/localtime && \
    ln -s "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime

COPY requirements.txt /tmp/requirements.txt
RUN pip install -U pip && \
    pip install -r /tmp/requirements.txt && \
    # Configure the "operating system"
    # ln -s $(which pypy3) /usr/local/bin/python && \
    mkdir /usr/local/lib/pontomaisoumenos && \
    # Docker image clean up, reduces it size
    apt-get purge build-essential -qq && \
    apt-get autoclean -qq && apt-get autoremove -qq && \
    rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/*

COPY . /usr/local/lib/pontomaisoumenos/
WORKDIR /usr/local/lib/pontomaisoumenos
ENTRYPOINT ["python", "-m", "app.main"]
