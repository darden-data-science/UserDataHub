FROM ubuntu:20.04

ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      vim \
      less \
      python3 \
      python3-dev \
      python3-pip \
      python3-setuptools \
      python3-wheel \
      libssl-dev \
      libcurl4-openssl-dev \
      build-essential \
      sqlite3 \
      curl \
      dnsutils \
      && \
    apt-get purge && apt-get clean

ARG USERDATAHUB_USER=jovyan
ARG USERDATAHUB_UID=1000

ARG HOME=/home/jovyan

ENV LANG C.UTF-8

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${USERDATAHUB_UID} \
    --home ${HOME} \
    --force-badname \
    ${USERDATAHUB_USER}

RUN python3 -m pip install --upgrade --no-cache setuptools pip

# RUN apt-get update && \
#     apt-get install -y --no-install-recommends pkg-config libxmlsec1-dev && \
#     apt-get purge && apt-get clean

COPY . /src/UserDataHub

RUN python3 -m pip install /src/UserDataHub && \
    rm -rf tmp/UserDataHub

WORKDIR /srv/userdatahub

RUN chown ${USERDATAHUB_USER}:${USERDATAHUB_USER} /srv/userdatahub

# COPY authhub_config.py /etc/auth_server/authhub_config.py

# RUN chown -R ${AUTH_SERVER_USER}:${AUTH_SERVER_USER} /etc/auth-server/authhub_config.yaml

EXPOSE 8000

USER ${USERDATAHUB_USER}

CMD ["userdatahub", "--config", "/etc/userdatahub/userdatahub_config.json"]