.PHONY:

DOCKER_IMAGE_VERSION := latest
REMOTE_REGISTRY := docker.io
REMOTE_USERNAME := macunha1
RUN_MIGRATIONS := no
TARGET_MONTH := ""
TARGET_YEAR := ""

tests:
	flake8 .
	py.test tests/punches.py --disable-pytest-warnings

docker: tests
	docker build -t ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION} .

dev: docker
	APP_DOCKER_IMAGE="${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION}" \
	RUN_MIGRATIONS="${RUN_MIGRATIONS}" \
	TARGET_MONTH="${TARGET_MONTH}" \
		docker-compose up -d

deploy: docker
	docker tag ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION} \
		${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION}
