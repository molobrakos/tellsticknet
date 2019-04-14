IMAGE=molobrakos/tellsticknet

default: check

format: white

white: black

black:
	white setup.py tellsticknet

lint:
	tox -e lint

test:
	tox

check: lint test

clean:
	rm -rf *.egg-info
	rm -rf .tox
	rm -rf .pytest_cache
	rm -rf dist
	rm -rf .cache
	rm -f *~
	rm -f .*~

pypi:
	rm -f dist/*.tar.gz
	python3 setup.py sdist
	twine upload dist/*.tar.gz

release:
	git diff-index --quiet HEAD -- && make check && bumpversion patch && git push --tags && git push && make pypi

docker-build:
	docker build -t $(IMAGE) .

docker-run-mqtt:
	docker run \
                --name=tellsticknet \
		--restart=always \
		--detach \
		--net=bridge \
		-p 30303:30303/udp \
		-p 42314:42314/udp \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		-v $(HOME)/.config/tellsticknet.conf:/app/tellsticknet.conf:ro \
		$(IMAGE) -vv

docker-run-mqtt-term:
	docker run \
		-ti --rm \
                --name=tellsticknet \
		--net=bridge \
		-p 30303:30303/udp \
		-p 42314:42314/udp \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		-v $(HOME)/.config/tellsticknet.conf:/app/tellsticknet.conf:ro \
		$(IMAGE) -vv
