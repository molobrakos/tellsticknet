FROM python:3.6-slim

WORKDIR /app

RUN set -x \
&& apt-get update && apt-get -y install git libsodium-dev \
&& git clone https://github.com/molobrakos/tellsticknet.git \
&& pip3 install -r tellsticknet/requirements.txt \
&& pip3 install coloredlogs libnacl \
;
