.PHONY:

DOCKER_IMAGE_VERSION := latest
REMOTE_REGISTRY := docker.io
REMOTE_USERNAME := macunha1
TARGET_MONTH := 10

tests:
	flake8 .
	# pytest .

docker: tests
	docker build -t ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION} .

dev: docker
	APP_DOCKER_IMAGE="${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION}" \
	DESIRED_MONTH="${TARGET_MONTH}" \
		docker-compose up -d

deploy: docker
	docker tag ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION} \
		${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:$(date -u --iso-8601)
	docker push ${REMOTE_REGISTRY}/${REMOTE_USERNAME}/pontomenosmenos:${DOCKER_IMAGE_VERSION}
