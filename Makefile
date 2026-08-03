# Nemo Anki — developer Makefile
#
# Targets run inside the docker-compose services so there's nothing to set
# up locally beyond Docker Desktop.

.PHONY: help up down build logs verify test test-backend typecheck-frontend \
        migrate makemigrations seed-decks shell-backend shell-db createsuperuser

help:
	@echo "Common targets:"
	@echo "  make up                 — start the stack (build + run, foreground)"
	@echo "  make down               — stop the stack"
	@echo "  make build              — rebuild images"
	@echo "  make logs               — tail backend + frontend + celery logs"
	@echo "  make verify             — backend tests + frontend typecheck"
	@echo "  make test-backend       — Django tests (incl. scheduler suite)"
	@echo "  make typecheck-frontend — tsc --noEmit on the frontend"
	@echo "  make migrate            — apply Django migrations"
	@echo "  make makemigrations     — generate Django migrations"
	@echo "  make seed-decks         — seed Menschen + Oxford deck trees"
	@echo "  make createsuperuser    — create a Django admin user"
	@echo "  make shell-backend      — bash inside the backend container"
	@echo "  make shell-db           — psql against the dev database"

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f backend frontend celery-worker celery-beat telegram-poller

test test-backend:
	docker compose exec backend python manage.py test

typecheck-frontend:
	docker compose exec frontend npx tsc --noEmit

verify: test-backend typecheck-frontend
	@echo "✓ backend tests pass and frontend typechecks"

migrate:
	docker compose exec backend python manage.py migrate

makemigrations:
	docker compose exec backend python manage.py makemigrations

seed-decks:
	docker compose exec backend python manage.py seed_decks

createsuperuser:
	docker compose exec backend python manage.py createsuperuser

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec db psql -U nemo -d nemo_anki
