FROM pypy:3-6-slim-jessie

COPY requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install build-essential -qq && \
    pip install -r /tmp/requirements.txt && \
	apt-get purge build-essential -qq && \
    ln -s $(which pypy3) /usr/local/bin/python && \
	apt-get autoclean -qq && apt-get autoremove -qq && \
	rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/*
COPY *.py /usr/local/bin/

ENTRYPOINT python /usr/local/bin/main.py
