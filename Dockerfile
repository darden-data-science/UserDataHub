FROM ubuntu:18.04

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


# ARG HOME=/home/jovyan

ENV LANG C.UTF-8

# RUN adduser --disabled-password \
#     --gecos "Default user" \
#     --uid ${AUTH_SERVER_UID} \
#     --home ${HOME} \
#     --force-badname \
#     ${AUTH_SERVER_USER}

RUN python3 -m pip install --upgrade --no-cache setuptools pip

RUN apt-get update && \
    apt-get install -y --no-install-recommends pkg-config libxmlsec1-dev && \
    apt-get purge && apt-get clean

COPY . /src/UserDataHub

RUN python3 -m pip install /src/UserDataHub && \
    rm -rf tmp/UserDataHub

COPY ./profile_files /etc/userdatahub/profile_files

WORKDIR /srv/userdatahub

# RUN chown ${AUTH_SERVER_USER}:${AUTH_SERVER_USER} /srv/auth_server

# COPY authhub_config.py /etc/auth_server/authhub_config.py

# RUN chown -R ${AUTH_SERVER_USER}:${AUTH_SERVER_USER} /etc/auth-server/authhub_config.yaml

EXPOSE 8000

USER ${AUTH_SERVER_USER}

CMD ["auth_server", "--config", "/etc/userdatahub/userdatahub_config.json"]