#!/bin/sh
#
# Daily backup of the whole Gardiner Lab stack to a network drive.
#
# Databases are copied with SQLite's online backup, so the applications can
# keep writing while it runs and the copy is never torn. Every copy is then
# integrity-checked and counted before it is kept, the archive is written to a
# temporary name and only renamed into place once complete, and the result is
# verified again after it reaches the network drive.
#
#   backup.sh            take a backup now
#   backup.sh --check    report on the destination and the last backup
#
# Exit codes: 0 success, 1 failure (the reason is logged and recorded in
# status.json so a monitor can pick it up).

set -u

DEST="${BACKUP_DEST:-/backup}"
STAGING="${BACKUP_STAGING:-/tmp/backup-staging}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-8}"
KEEP_MONTHLY="${KEEP_MONTHLY:-12}"
SENTINEL="$DEST/.backup-target"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
NAME="lab-suite-${STAMP}"
LOG="$DEST/backup.log"

log() {
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
    [ -w "$DEST" ] 2>/dev/null && printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

# Record the outcome where a monitor (or the healthcheck) can read it.
write_status() {
    status="$1"; detail="$2"; archive="${3:-}"
    [ -d "$DEST" ] || return 0
    cat > "$DEST/status.json.part" <<EOF
{
  "status": "$status",
  "detail": "$detail",
  "archive": "$archive",
  "finished_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "host": "$(hostname)"
}
EOF
    mv "$DEST/status.json.part" "$DEST/status.json" 2>/dev/null || true
}

fail() {
    log "FAILED: $*"
    write_status "failed" "$*"
    [ -n "${NOTIFY_URL:-}" ] && wget -q -O- --post-data="{\"text\":\"Lab suite backup FAILED: $*\"}" \
        --header='Content-Type: application/json' "$NOTIFY_URL" >/dev/null 2>&1
    rm -rf "$STAGING"
    exit 1
}

# ---------------------------------------------------------------------------
# The destination must be the real network drive, not an empty mount point
# ---------------------------------------------------------------------------
check_destination() {
    [ -d "$DEST" ] || fail "destination $DEST does not exist inside the container"
    if [ ! -f "$SENTINEL" ]; then
        fail "no .backup-target marker in $DEST. If the network drive is mounted, run 'make backup-init' once to mark it. This guard exists so that a drive which failed to mount is never mistaken for the backup target."
    fi
    touch "$DEST/.write-test" 2>/dev/null || fail "destination $DEST is not writable"
    rm -f "$DEST/.write-test"
}

if [ "${1:-}" = "--check" ]; then
    echo "Destination : $DEST"
    if [ -f "$SENTINEL" ]; then echo "Marker      : present"; else echo "Marker      : MISSING - run 'make backup-init'"; fi
    echo "Free space  : $(df -h "$DEST" 2>/dev/null | awk 'NR==2 {print $4" of "$2}')"
    echo "Archives    : $(find "$DEST" -name 'lab-suite-*.tar.gz' 2>/dev/null | wc -l)"
    echo "Last status : $(cat "$DEST/status.json" 2>/dev/null || echo 'none recorded')"
    exit 0
fi

check_destination
log "starting backup $NAME"
rm -rf "$STAGING"
mkdir -p "$STAGING/$NAME/databases" "$STAGING/$NAME/files" || fail "could not create staging area"

# ---------------------------------------------------------------------------
# Databases: online backup, then verify the copy
# ---------------------------------------------------------------------------
DB_REPORT=""
backup_db() {
    label="$1"; src="$2"
    if [ ! -f "$src" ]; then
        log "  $label: not present, skipping"
        return 0
    fi
    out="$STAGING/$NAME/databases/$(basename "$src")"
    # .backup uses SQLite's online backup API: safe while the app is writing.
    sqlite3 "file:$src?mode=ro" ".backup '$out'" 2>/dev/null \
        || fail "could not copy $label from $src"

    check="$(sqlite3 "$out" 'PRAGMA integrity_check;' 2>&1 | head -1)"
    [ "$check" = "ok" ] || fail "$label failed its integrity check after copying: $check"

    tables="$(sqlite3 "$out" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)"
    size="$(wc -c < "$out" | tr -d ' ')"
    log "  $label: ok, ${size} bytes, ${tables} tables"
    DB_REPORT="${DB_REPORT}    {\"name\": \"$(basename "$src")\", \"label\": \"$label\", \"bytes\": $size, \"tables\": $tables, \"integrity\": \"ok\"},
"
}

backup_db "MoClo main"      "${MOCLO_DB:-/moclo/moclo.db}"
backup_db "MoClo parts"     "${PARTS_DB:-/moclo/parts.db}"
backup_db "Plasmid Editor"  "${EDITOR_DB:-/data/plasmid_editor.db}"

[ -n "$DB_REPORT" ] || fail "no databases were found to back up - check the volume mounts"

# ---------------------------------------------------------------------------
# Anything else living in the volumes, and the stack's configuration
# ---------------------------------------------------------------------------
copy_extras() {
    label="$1"; dir="$2"
    [ -d "$dir" ] || return 0
    # Everything that is not a database we already copied properly.
    if find "$dir" -mindepth 1 -not -name '*.db' -not -name '*.db-wal' -not -name '*.db-shm' \
        | head -1 | grep -q .; then
        tar czf "$STAGING/$NAME/files/${label}.tar.gz" -C "$dir" \
            --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' . 2>/dev/null \
            && log "  $label extras: archived"
    fi
}
copy_extras "moclo-volume"  "${MOCLO_DIR:-/moclo}"
copy_extras "editor-volume" "${EDITOR_DIR:-/data}"

if [ -d "${CONFIG_DIR:-/config}" ]; then
    # Compose files, nginx routing and the landing page: enough to rebuild the
    # stack. Secrets are deliberately left out; see docs/BACKUP.md.
    tar czf "$STAGING/$NAME/files/config.tar.gz" -C "${CONFIG_DIR:-/config}" \
        --exclude='.env' --exclude='*.key' --exclude='*.pem' --exclude='.git' . 2>/dev/null \
        && log "  stack configuration: archived (secrets excluded)"
fi

# ---------------------------------------------------------------------------
# Manifest, archive, and verification at the destination
# ---------------------------------------------------------------------------
cat > "$STAGING/$NAME/manifest.json" <<EOF
{
  "archive": "$NAME",
  "created_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "host": "$(hostname)",
  "databases": [
$(printf '%s' "$DB_REPORT" | sed '$ s/,$//')
  ]
}
EOF

ARCHIVE="$DEST/$NAME.tar.gz"
tar czf "$ARCHIVE.part" -C "$STAGING" "$NAME" || fail "could not write the archive to $DEST"

# A truncated transfer must never look like a good backup: verify the archive
# can be read back in full, and only then put it in place.
tar tzf "$ARCHIVE.part" >/dev/null 2>&1 || fail "the archive written to $DEST is unreadable"
mv "$ARCHIVE.part" "$ARCHIVE" || fail "could not finalise the archive"

cd "$DEST" || fail "cannot enter $DEST"
sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256" 2>/dev/null
sha256sum -c "$NAME.tar.gz.sha256" >/dev/null 2>&1 \
    || fail "the archive does not match its checksum after being written"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
log "wrote $NAME.tar.gz ($SIZE), checksum verified"

# ---------------------------------------------------------------------------
# Retention: keep recent dailies, one per week, one per month
# ---------------------------------------------------------------------------
prune() {
    keep="$(mktemp)"
    seen_weeks=""
    seen_months=""
    index=0

    # Newest first: keep the recent dailies outright, then the newest archive
    # of each week and of each month, so older history thins instead of
    # disappearing all at once.
    for archive in $(ls -1t "$DEST"/lab-suite-*.tar.gz 2>/dev/null); do
        day="$(basename "$archive" | sed -n 's/^lab-suite-\([0-9][0-9-]*\)_.*/\1/p')"
        week="$(date -d "$day" +%G-%V 2>/dev/null || echo "$day")"
        month="$(echo "$day" | cut -c1-7)"
        index=$((index + 1))
        keep_this=0
        [ "$index" -le "$KEEP_DAILY" ] && keep_this=1

        case " $seen_weeks " in
            *" $week "*) ;;
            *)  seen_weeks="$seen_weeks $week"
                [ "$(echo "$seen_weeks" | wc -w)" -le "$KEEP_WEEKLY" ] && keep_this=1 ;;
        esac
        case " $seen_months " in
            *" $month "*) ;;
            *)  seen_months="$seen_months $month"
                [ "$(echo "$seen_months" | wc -w)" -le "$KEEP_MONTHLY" ] && keep_this=1 ;;
        esac

        [ "$keep_this" -eq 1 ] && echo "$archive" >> "$keep"
    done

    removed=0
    for archive in $(ls -1 "$DEST"/lab-suite-*.tar.gz 2>/dev/null); do
        # Whole-line match: a substring test would keep files by accident.
        if ! grep -qxF "$archive" "$keep" 2>/dev/null; then
            rm -f "$archive" "$archive.sha256"
            removed=$((removed + 1))
        fi
    done
    rm -f "$keep"
    [ "$removed" -gt 0 ] && log "pruned $removed old archive(s)"
    return 0
}

# Pruning is housekeeping. The archive is already written and verified, so a
# problem here must be reported without the run being recorded as a failure.
( prune ) || log "warning: pruning old archives did not complete"

rm -rf "$STAGING"
REMAINING="$(find "$DEST" -name 'lab-suite-*.tar.gz' | wc -l | tr -d ' ')"
log "backup complete: $REMAINING archive(s) held, $(df -h "$DEST" | awk 'NR==2 {print $4}') free"
write_status "ok" "$REMAINING archive(s) held" "$NAME.tar.gz"

[ -n "${NOTIFY_ON_SUCCESS:-}" ] && [ -n "${NOTIFY_URL:-}" ] && \
    wget -q -O- --post-data="{\"text\":\"Lab suite backup ok: $NAME.tar.gz ($SIZE)\"}" \
        --header='Content-Type: application/json' "$NOTIFY_URL" >/dev/null 2>&1
exit 0
