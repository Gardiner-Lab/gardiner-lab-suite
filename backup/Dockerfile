# Backup sidecar and console for the Gardiner Lab stack.
#
# Deliberately dependency-light: the sqlite3 CLI for online database copies, jq
# to read the settings the console writes, and Flask for the console itself. It
# needs no access to the Docker socket, because both backup and restore use
# SQLite's online backup API and never require the applications to stop.
FROM alpine:3.20

RUN apk add --no-cache sqlite tzdata jq python3 py3-flask py3-bcrypt

COPY backup.sh restore.sh entrypoint.sh app.py console.html /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/entrypoint.sh

ENV BACKUP_DEST=/backup \
    CONFIG_STORE=/config-store \
    BACKUP_HOUR=2 \
    BACKUP_MINUTE=30 \
    KEEP_DAILY=14 \
    KEEP_WEEKLY=8 \
    KEEP_MONTHLY=12 \
    TZ=Europe/Amsterdam

# Unhealthy when the last backup did not succeed, or is more than 36 hours old,
# so a silently broken backup shows up in `docker ps` rather than being noticed
# the day it is needed.
HEALTHCHECK --interval=1h --timeout=10s --start-period=1m --retries=1 \
    CMD /usr/local/bin/entrypoint.sh healthcheck

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["schedule"]
