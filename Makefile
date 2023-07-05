venv:
	python3 -m venv ./venv
deps: venv
	. ./venv/bin/activate
	pip install tox
build-image:
	docker build --target build \
	--tag openfga:latest \
	./images
push-microk8s: build-image
	docker tag openfga:latest localhost:32000/openfga:latest
	docker push localhost:32000/openfga:latest