FROM python:3.7-slim-buster
# FROM pypy:3-7.3.0-slim-buster -> not yet

ARG TIMEZONE

# Reducing the quantity of image layers through less commands
RUN apt-get update && \
    apt-get install -y build-essential \
        libpq-dev && \
    [ -f /etc/localtime ] && rm -f /etc/localtime && \
    # if TIMEZONE is null, fallback to UTC-3 (America/Sao_Paulo)
    ln -s "/usr/share/zoneinfo/${TIMEZONE:-America/Sao_Paulo}" \
        /etc/localtime

# Installing the dependencies before copying the code
#   to take advantage of the Docker layer caching for deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install -U pip && \
    pip install -r /tmp/requirements.txt && \
    # Configure the "operating system"
    # ln -s $(which pypy3) /usr/local/bin/python && \
    mkdir /usr/local/lib/pontomaisoumenos

# Docker image clean up, reduces the overall size
RUN apt-get purge build-essential -y && \
    apt-get autoclean -y && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/*

COPY . /usr/local/lib/pontomaisoumenos/
WORKDIR /usr/local/lib/pontomaisoumenos
ENTRYPOINT ["python", "-m", "app.main"]
