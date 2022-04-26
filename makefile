all: clean test

init:
	docker pull centos
	docker-compose build

test:
	docker-compose up -d
	sleep 1
	python ./tests/httptest.py
	docker-compose down

clean:
	find . -name '*.pyc' -delete
	docker-compose down
