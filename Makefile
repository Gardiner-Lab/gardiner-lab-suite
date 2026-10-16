.PHONY: help install up down logs pull update restart-proxy local check certs         backup backup-init backup-check backup-list backup-logs restore restore-check

help:
	@echo "Gardiner Lab Tools - available commands"
	@echo "======================================="
	@echo "install       - Install or update; takes over an existing MoClo"
	@echo "up            - Start the suite (needs SECRET_KEY and MOCLO_SECRET_KEY)"
	@echo "down          - Stop the suite"
	@echo "logs          - Follow the logs"
	@echo "update        - Pull new images and restart"
	@echo "restart-proxy - Reload the landing page and routing only"
	@echo "local         - Build the editor from ../plasmid-editor instead of pulling"
	@echo "check         - Verify every route answers"
	@echo "certs         - Make or renew the https certificate (docs/HTTPS.md)"
	@echo ""
	@echo "Backups"
	@echo "  backup-init   - Mark the mounted network drive as the backup destination (once)"
	@echo "  backup        - Take a backup now, instead of waiting for the nightly run"
	@echo "  backup-check  - Destination, free space and the last run's result"
	@echo "  backup-list   - List the archives held"
	@echo "  backup-logs   - Follow the backup container's log"
	@echo "  restore-check - Verify an archive without changing anything (ARCHIVE=...)"
	@echo "  restore       - Restore from an archive (ARCHIVE=latest), stack stopped"

install:
	./install.sh

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

certs:
	./scripts/make-certs.sh
	docker compose restart proxy

# --- backups ----------------------------------------------------------------

backup-init:
	docker compose run --rm backup init

backup:
	docker compose run --rm backup now

backup-check:
	docker compose run --rm backup check

backup-list:
	docker compose --profile restore run --rm restore restore --list

backup-logs:
	docker compose logs -f backup

restore-check:
	docker compose --profile restore run --rm restore restore --dry-run $(or $(ARCHIVE),latest)

# Restoring replaces the live databases, so the applications are stopped first
# and started again afterwards. The replaced files are kept as .before-restore.
restore:
	@echo "Stopping the applications so nothing writes during the restore..."
	docker compose stop moclo editor
	docker compose --profile restore run --rm restore restore $(or $(ARCHIVE),latest)
	docker compose start moclo editor
	@echo "Applications restarted."
