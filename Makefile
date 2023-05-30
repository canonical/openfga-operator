venv:
	python3 -m venv ./venv
deps: venv
	. ./venv/bin/activate
	pip install tox
build-image:
	docker build --target build \
	--tag openfga:latest \
	./images

