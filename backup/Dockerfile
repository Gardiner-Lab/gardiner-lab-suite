# Backup sidecar for the Gardiner Lab stack.
#
# Deliberately tiny and dependency-light: busybox cron for the schedule and the
# sqlite3 CLI for online database copies. It needs no access to the Docker
# socket, because SQLite's online backup works while the applications write.
FROM alpine:3.20

RUN apk add --no-cache sqlite tzdata

COPY backup.sh restore.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/entrypoint.sh

ENV BACKUP_DEST=/backup \
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
