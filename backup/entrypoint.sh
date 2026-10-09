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
DEST="${BACKUP_DEST:-/backup}"

case "${1:-schedule}" in

  now)
    exec /usr/local/bin/backup.sh
    ;;

  check)
    exec /usr/local/bin/backup.sh --check
    ;;

  init)
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
    [ -f "$DEST/status.json" ] || { echo "no backup has run yet"; exit 1; }
    grep -q '"status": *"ok"' "$DEST/status.json" || { echo "last backup failed"; exit 1; }
    # Older than 36 hours means a daily run has been missed.
    if [ -n "$(find "$DEST/status.json" -mmin +2160 2>/dev/null)" ]; then
        echo "last backup is more than 36 hours old"
        exit 1
    fi
    echo "last backup ok"
    ;;

  restore)
    shift
    exec /usr/local/bin/restore.sh "$@"
    ;;

  schedule)
    HOUR="${BACKUP_HOUR:-2}"
    MIN="${BACKUP_MINUTE:-30}"
    mkdir -p /etc/crontabs
    echo "$MIN $HOUR * * * /usr/local/bin/backup.sh >/proc/1/fd/1 2>/proc/1/fd/2" > /etc/crontabs/root
    echo "Backup scheduled daily at $(printf '%02d:%02d' "$HOUR" "$MIN") ${TZ:-UTC}, writing to $DEST"
    if [ ! -f "$DEST/.backup-target" ]; then
        echo "WARNING: $DEST is not marked as a backup destination yet."
        echo "         Run 'make backup-init' once, with the network drive mounted."
    fi
    # -f foreground, -d 8 so cron's own messages reach the container log.
    exec crond -f -d 8
    ;;

  *)
    exec "$@"
    ;;
esac
