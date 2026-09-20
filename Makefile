PROJECT_NAME	= payout_gateway
PROJECT_VERSION	= $(shell poetry version -s)
PACKAGE_NAME	= payout_gateway
TEST_DB = payout_gateway_test

lint:
	poetry run ruff check --fix .
	poetry run flake8 ${PACKAGE_NAME}
	poetry run mypy ${PACKAGE_NAME}

fmt:
	poetry run ruff format .

spec:
	poetry run payout_gateway spec

test:


down:
	docker compose down

build:
	docker compose build

up:
	docker compose up

run: down fmt build up


test-db:
	@docker exec db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='$(TEST_DB)'" | grep -q 1 \
		|| docker exec db psql -U postgres -c "CREATE DATABASE $(TEST_DB)"

test: test-db
	POSTGRES_HOST=localhost poetry run pytest

check:
	poetry run ruff check payout_gateway tests
	poetry run mypy payout_gateway