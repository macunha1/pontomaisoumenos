.PHONY: tests docker save-docker-image load-docker-image dev deploy

DOCKER_IMAGE_VERSION := latest
REMOTE_REGISTRY := docker.io
REMOTE_USERNAME := $${USER}
CACHE_DIR := ${HOME}/.cache
RUN_MIGRATIONS := no

tests:
	flake8 --max-line-length=120 .
	PYTHONPATH=${PWD} py.test tests/punches.py --disable-pytest-warnings

docker:
	docker build \
		--build-arg TIMEZONE="$(shell [ -f /etc/TZ ] && cat /etc/TZ || readlink -f /etc/localtime )" \
		-t ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:${DOCKER_IMAGE_VERSION} .

save-docker-image:
	docker save -o ${CACHE_DIR}/pontomaisoumenos.tar \
		${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:${DOCKER_IMAGE_VERSION}

load-docker-image:
	docker load -i ${CACHE_DIR}/pontomaisoumenos.tar || true

dev: docker
	APP_DOCKER_IMAGE="${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:${DOCKER_IMAGE_VERSION}" \
	RUN_MIGRATIONS="${RUN_MIGRATIONS}" \
		docker-compose up -d

docker-push: docker
	docker tag ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:${DOCKER_IMAGE_VERSION} \
		${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomaisoumenos:${DOCKER_IMAGE_VERSION}
