FROM python:3.6.7-slim-jessie

COPY requirements.txt /tmp/requirements.txt
RUN printf "deb http://archive.debian.org/debian/ jessie main\ndeb-src http://archive.debian.org/debian/ jessie main\ndeb http://security.debian.org jessie/updates main\ndeb-src http://security.debian.org jessie/updates main" > /etc/apt/sources.list
RUN apt-get update && \
    apt-get install -y --no-install-recommends apt-utils && \
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