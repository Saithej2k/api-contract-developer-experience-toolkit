.PHONY: setup test test-backend test-client openapi generate-client docker-up docker-down clean

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r backend/requirements.txt
	npm --prefix client ci

openapi:
	.venv/bin/python scripts/export_openapi.py

generate-client: openapi
	npm --prefix client run generate

test-backend:
	.venv/bin/python -m pytest backend/tests -q

test-client:
	npm --prefix client run build
	npm --prefix client test
	npm --prefix client run test:playwright

test: test-backend generate-client test-client

docker-up:
	docker compose up --build

docker-down:
	docker compose down --volumes

clean:
	rm -rf .pytest_cache client/dist client/coverage client/playwright-report client/test-results
