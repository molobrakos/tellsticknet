IMAGE=molobrakos/tellsticknet

default: check

lint:
	tox -e lint

test:
	tox

check: lint test

docker-build:
	docker build -t $(IMAGE) .

docker-run-mqtt:
	docker run \
                --name tellsticknet \
		--restart always \
		--detach \
		--net host \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		-v $(HOME)/.config/tellsticknet.conf:/app/tellsticknet.conf:ro \
		$(IMAGE) -vv

docker-run-mqtt-term:
	docker run \
		-ti --rm \
                --name tellsticknet \
		--net host \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		-v $(HOME)/.config/tellsticknet.conf:/app/tellsticknet.conf:ro \
		$(IMAGE) -vv
