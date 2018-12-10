# FROM pypy:3-6-slim-jessie
FROM python:3.6.7-slim-jessie

COPY requirements.txt /tmp/requirements.txt
RUN apt-get update && \
    # Install Dependencies
    apt-get install build-essential -qq \
        libpq-dev && \
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
