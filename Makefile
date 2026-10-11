# One command per job. Ports: the dashboard on PORT, Django on API_PORT, both on 127.0.0.1.
# Settings come from the environment or an optional .env file (see .env.example).
-include .env
export
PORT ?= 4124
API_PORT ?= 14124
HOST := 127.0.0.1
API_URL := http://$(HOST):$(API_PORT)

BACK := cd backend &&
FRONT := cd frontend &&
CONCURRENTLY := frontend/node_modules/.bin/concurrently -n api,worker,web,ready -c blue,magenta,green,gray
API_ENV := SITEMEND_SELF_URL=$(API_URL)
WORKER := uv run celery -A config worker --pool=threads --concurrency=4 --loglevel=INFO --without-gossip --without-mingle

.PHONY: install migrate dev build start start-replay test test-backend test-frontend record reset

install:
	$(BACK) uv sync --frozen
	$(FRONT) npm ci

migrate:
	$(BACK) uv run python manage.py migrate --noinput

# Development: Django runserver, a Celery worker and next dev, with prefixed logs.
dev: migrate
	$(CONCURRENTLY) \
	  "$(BACK) $(API_ENV) DJANGO_DEBUG=1 uv run python manage.py runserver $(HOST):$(API_PORT) --noreload" \
	  "$(BACK) $(API_ENV) $(WORKER)" \
	  "$(FRONT) SITEMEND_API_URL=$(API_URL) npx next dev -H $(HOST) -p $(PORT)" \
	  "scripts/wait-ready.sh $(API_URL) http://$(HOST):$(PORT)"

build:
	$(FRONT) SITEMEND_API_URL=$(API_URL) npx next build

# Production: next build, then gunicorn, the Celery worker and next start.
start: migrate build
	$(CONCURRENTLY) \
	  "$(BACK) $(API_ENV) uv run gunicorn config.wsgi -b $(HOST):$(API_PORT) --workers 1 --threads 8" \
	  "$(BACK) $(API_ENV) $(WORKER)" \
	  "$(FRONT) npx next start -H $(HOST) -p $(PORT)" \
	  "scripts/wait-ready.sh $(API_URL) http://$(HOST):$(PORT)"

# Same as start, with recorded model sessions instead of the live model.
start-replay:
	DEMO_REPLAY=1 $(MAKE) start

test: test-backend test-frontend

test-backend:
	$(BACK) uv run pytest

test-frontend:
	$(FRONT) npx tsc --noEmit && npx eslint .

# Re-record replay fixtures from a live run, on a scratch database.
record:
	$(BACK) export SITEMEND_VAR_DIR=$$(mktemp -d) && uv run python manage.py migrate -v0 && uv run python manage.py record_fixtures

reset:
	$(BACK) uv run python manage.py reset_demo
