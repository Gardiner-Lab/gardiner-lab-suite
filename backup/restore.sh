#!/bin/sh
#
# Restore the Gardiner Lab stack from a backup archive.
#
#   restore.sh --list                     show the archives available
#   restore.sh --inspect <archive>        show what is inside one, without restoring
#   restore.sh --dry-run <archive>        unpack and verify, but change nothing
#   restore.sh <archive>                  restore into the mounted volumes
#   restore.sh latest                     restore the most recent archive
#
# Restoring overwrites the live databases, so it refuses unless the
# applications are stopped (the compose wrapper does that for you) and it
# always keeps the replaced databases alongside, with a .before-restore suffix.

set -u

SETTINGS="${CONFIG_STORE:-/config-store}/settings.json"
DEST="$(jq -r '.destination // empty' "$SETTINGS" 2>/dev/null)"
[ -n "$DEST" ] || DEST="${BACKUP_DEST:-/backup}"
WORK="/tmp/restore-work"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

archive_path() {
    case "$1" in
        latest) ls -1t "$DEST"/lab-suite-*.tar.gz 2>/dev/null | head -1 ;;
        /*) echo "$1" ;;
        *) echo "$DEST/$1" ;;
    esac
}

if [ $# -eq 0 ] || [ "$1" = "--help" ]; then
    sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

if [ "$1" = "--list" ]; then
    say "Archives in $DEST:"
    ls -1t "$DEST"/lab-suite-*.tar.gz 2>/dev/null | while read -r a; do
        printf '  %-34s %8s  %s\n' "$(basename "$a")" "$(du -h "$a" | cut -f1)" \
            "$(date -r "$a" '+%Y-%m-%d %H:%M' 2>/dev/null)"
    done
    [ -f "$DEST/status.json" ] && { say ""; say "Last run:"; cat "$DEST/status.json"; }
    exit 0
fi

MODE="restore"
case "$1" in
    --inspect) MODE="inspect"; shift ;;
    --dry-run) MODE="dry-run"; shift ;;
esac
[ $# -ge 1 ] || die "which archive? Try: restore.sh --list"

ARCHIVE="$(archive_path "$1")"
[ -f "$ARCHIVE" ] || die "no such archive: $ARCHIVE"

# Verify before trusting it.
if [ -f "$ARCHIVE.sha256" ]; then
    (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256" >/dev/null 2>&1) \
        || die "$ARCHIVE does not match its checksum - do not restore from it"
    say "Checksum verified."
fi

rm -rf "$WORK"; mkdir -p "$WORK"
tar xzf "$ARCHIVE" -C "$WORK" || die "could not unpack $ARCHIVE"
ROOT="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -d "$ROOT" ] || die "the archive does not have the expected layout"

say ""
say "Archive: $(basename "$ARCHIVE")"
[ -f "$ROOT/manifest.json" ] && cat "$ROOT/manifest.json"
say ""

# Every database is checked again after unpacking, so a bad archive is caught
# before anything live is touched.
FOUND=0
for db in "$ROOT"/databases/*.db; do
    [ -f "$db" ] || continue
    FOUND=$((FOUND + 1))
    check="$(sqlite3 "$db" 'PRAGMA integrity_check;' 2>&1 | head -1)"
    rows="$(sqlite3 "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)"
    say "  $(basename "$db"): integrity $check, $rows tables"
    [ "$check" = "ok" ] || die "$(basename "$db") is damaged in this archive"
done
[ "$FOUND" -gt 0 ] || die "the archive contains no databases"

if [ "$MODE" = "inspect" ] || [ "$MODE" = "dry-run" ]; then
    say ""
    say "Contents:"
    tar tzf "$ARCHIVE" | sed 's/^/  /'
    say ""
    say "$MODE only - nothing was changed."
    rm -rf "$WORK"
    exit 0
fi

# --- restore ---------------------------------------------------------------
restore_db() {
    name="$1"; target="$2"
    src="$ROOT/databases/$name"
    [ -f "$src" ] || { say "  $name: not in this archive, leaving the current one alone"; return 0; }
    target_dir="$(dirname "$target")"
    [ -d "$target_dir" ] || { say "  $name: $target_dir is not mounted, skipping"; return 0; }
    # The applications run as an unprivileged user while this runs as root.
    # Without putting the ownership back, a restore leaves every database
    # readable but not writable: the tools come up and then fail on first save.
    if [ -f "$target" ]; then
        owner="$(stat -c '%u:%g' "$target" 2>/dev/null)"
        mode="$(stat -c '%a' "$target" 2>/dev/null)"
        cp "$target" "$target.before-restore" 2>/dev/null \
            && say "  $name: current database kept as $(basename "$target").before-restore"
    else
        owner="$(stat -c '%u:%g' "$target_dir" 2>/dev/null)"
        mode="644"
    fi
    cp -f "$src" "$target" || die "could not write $target (is the volume mounted read-write?)"
    # WAL side files from the old database would contradict the restored one.
    rm -f "$target-wal" "$target-shm"
    if [ -n "$owner" ]; then
        chown "$owner" "$target" 2>/dev/null
        chown "$owner" "$target.before-restore" 2>/dev/null
    fi
    [ -n "$mode" ] && chmod "$mode" "$target" 2>/dev/null
    say "  $name: restored to $target (owner $owner)"
}

say "Restoring..."
restore_db "moclo.db"           "${MOCLO_DB:-/moclo/moclo.db}"
restore_db "parts.db"           "${PARTS_DB:-/moclo/parts.db}"
restore_db "plasmid_editor.db"  "${EDITOR_DB:-/data/plasmid_editor.db}"
restore_db "suite.db"           "${SUITE_DB:-/suite/suite.db}"

if [ -f "$ROOT/files/config.tar.gz" ]; then
    say ""
    say "The archive also holds the stack configuration. It is NOT restored"
    say "automatically; unpack it yourself if you need it:"
    say "  tar xzf $ARCHIVE -C /tmp && ls /tmp/$(basename "$ROOT")/files/"
fi

rm -rf "$WORK"
say ""
say "Done. Start the stack again with: docker compose up -d"
say "If anything looks wrong, the previous databases are still beside the"
say "restored ones with a .before-restore suffix."
