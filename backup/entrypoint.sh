#!/bin/sh
#
# Entry point for the backup sidecar.
#
#   schedule      run the daily backup on a cron schedule (the default)
#   now           take a backup immediately and exit
#   check         report on the destination and the last run
#   init          mark the destination as the real backup drive
#   healthcheck   succeed only if the last backup was recent and good
#   restore ...   hand over to restore.sh

set -u
SETTINGS_FILE="${CONFIG_STORE:-/config-store}/settings.json"
DEST="$(jq -r '.destination // empty' "$SETTINGS_FILE" 2>/dev/null)"
[ -n "$DEST" ] || DEST="${BACKUP_DEST:-/backup}"

case "${1:-schedule}" in

  now)
    exec /usr/local/bin/backup.sh
    ;;

  check)
    exec /usr/local/bin/backup.sh --check
    ;;

  init)
    if [ "$(jq -r '.destination_type // empty' "$SETTINGS_FILE" 2>/dev/null)" = "smb" ]; then
        echo "The destination is a network share: mark it from the backup console." >&2
        exit 1
    fi
    # Writing the marker is how an operator says "this really is the network
    # drive". backup.sh refuses to run without it, so a drive that failed to
    # mount cannot be mistaken for the destination.
    [ -d "$DEST" ] || { echo "Error: $DEST is not mounted in this container" >&2; exit 1; }
    cat > "$DEST/.backup-target" <<EOF
This directory is the backup destination for the Gardiner Lab tool suite.
Marked on $(date -u '+%Y-%m-%d %H:%M:%SZ') from $(hostname).

The backup refuses to run if this file is missing, so that an unmounted
network drive is never silently filled up instead.
EOF
    echo "Marked $DEST as the backup destination."
    ;;

  healthcheck)
    # The last outcome is kept in the settings volume, so checking health never
    # has to reach a network share. Older installs only have it at $DEST.
    STATUS="${CONFIG_STORE:-/config-store}/last-status.json"
    [ -f "$STATUS" ] || STATUS="$DEST/status.json"
    [ -f "$STATUS" ] || { echo "no backup has run yet"; exit 1; }
    grep -q '"status": *"ok"' "$STATUS" || { echo "last backup failed"; exit 1; }
    # Older than 36 hours means a daily run has been missed.
    if [ -n "$(find "$STATUS" -mmin +2160 2>/dev/null)" ]; then
        echo "last backup is more than 36 hours old"
        exit 1
    fi
    echo "last backup ok"
    ;;

  restore)
    shift
    exec /usr/local/bin/restore.sh "$@"
    ;;

  api)
    # The backup console: settings, run now, download/upload, restore.
    exec python3 /usr/local/bin/app.py
    ;;

  schedule)
    # A loop rather than cron, so a schedule changed in the console takes
    # effect without restarting anything.
    SETTINGS="${CONFIG_STORE:-/config-store}/settings.json"
    LAST_RUN="${CONFIG_STORE:-/config-store}/.last-run-day"
    echo "Backup scheduler started (settings: $SETTINGS)"
    while true; do
        hour="$(jq -r '.hour // 2' "$SETTINGS" 2>/dev/null || echo 2)"
        minute="$(jq -r '.minute // 30' "$SETTINGS" 2>/dev/null || echo 30)"
        enabled="$(jq -r '.enabled // true' "$SETTINGS" 2>/dev/null || echo true)"
        want="$(printf '%02d:%02d' "$hour" "$minute" 2>/dev/null || echo 02:30)"
        now="$(date +%H:%M)"
        today="$(date +%F)"
        if [ "$enabled" = "true" ] && [ "$now" = "$want" ] \
           && [ "$(cat "$LAST_RUN" 2>/dev/null || echo none)" != "$today" ]; then
            echo "$today" > "$LAST_RUN"
            echo "Running the scheduled backup for $today"
            /usr/local/bin/backup.sh || echo "scheduled backup failed"
        fi
        sleep 30
    done
    ;;

  *)
    exec "$@"
    ;;
esac
