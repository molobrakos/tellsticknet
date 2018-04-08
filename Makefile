IMAGE=tellsticknet

build:
	docker build -t $(IMAGE) .

docker-run:
	docker run \
		-ti --rm \
		--net=host \
		-v $(HOME)/.config/mosquitto_pub:/root/.config/mosquitto_pub:ro \
		-v $(HOME)/.tellsticknet.conf:/root/tellsticknet.conf:ro \
		$(IMAGE) ./tellsticknet/script/tellsticknet mqtt -vv
