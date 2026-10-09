.PHONY: help up down logs pull update restart-proxy local check

help:
	@echo "Gardiner Lab Tools - available commands"
	@echo "======================================="
	@echo "up            - Start the suite (needs SECRET_KEY and MOCLO_SECRET_KEY)"
	@echo "down          - Stop the suite"
	@echo "logs          - Follow the logs"
	@echo "update        - Pull new images and restart"
	@echo "restart-proxy - Reload the landing page and routing only"
	@echo "local         - Build the editor from ../plasmid-editor instead of pulling"
	@echo "check         - Verify every route answers"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

pull update:
	docker compose pull
	docker compose up -d

restart-proxy:
	docker compose restart proxy

local:
	docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

check:
	./scripts/check.sh
