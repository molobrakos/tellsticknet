FROM python:3.7-slim-stretch

WORKDIR /app

RUN set -x \
&& apt-get update \
&& apt-get -y --no-install-recommends install dumb-init libsodium18 \
&& apt-get -y autoremove \
&& apt-get -y clean \
&& rm -rf /var/lib/apt/lists/* \
&& rm -rf /tmp/* \
&& rm -rf /var/tmp/* \
&& useradd -M --home-dir /app tellstick \
  ;

COPY requirements.txt ./

RUN pip --no-cache-dir --trusted-host pypi.org install --upgrade -r requirements.txt pip coloredlogs libnacl \
  && rm requirements.txt \
  ;

USER tellstick

COPY . ./

ENTRYPOINT ["dumb-init", "--", "python3", "-m", "tellsticknet", "mqtt"]
