.PHONY: dev dev-down dev-logs dev-shell dev-rebuild prod-logs help

help:
	@echo "Flame backend — common dev commands"
	@echo ""
	@echo "  make dev          start local app + redis with hot reload (port 8000)"
	@echo "  make dev-down     stop local dev containers"
	@echo "  make dev-logs     tail logs from local app container"
	@echo "  make dev-shell    shell into the local app container"
	@echo "  make dev-rebuild  rebuild the app image (after requirements.txt changes)"
	@echo ""

dev:
	docker compose -f docker-compose.dev.yml up -d
	@echo ""
	@echo "Flame API running at http://localhost:8000"
	@echo "Docs at http://localhost:8000/docs"
	@echo "Use 'make dev-logs' to follow logs"

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f app

dev-shell:
	docker compose -f docker-compose.dev.yml exec app /bin/bash

dev-rebuild:
	docker compose -f docker-compose.dev.yml build --no-cache app
	docker compose -f docker-compose.dev.yml up -d
