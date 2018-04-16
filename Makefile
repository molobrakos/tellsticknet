IMAGE=tellsticknet

docker-build:
	docker build -t $(IMAGE) .

docker-run-mqtt:
	docker run \
		-ti --rm \
		--net=host \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		-v $(HOME)/.tellsticknet.conf:/app/tellsticknet.conf:ro \
		$(IMAGE) ./script/tellsticknet mqtt -vv
