# Sign-in, registration and labs for Trellis Tools: the proxy asks it
# who is signed in before every request to a tool.
FROM alpine:3.20

# cryptography and the CA list: the Hosting tab reads the certificate the proxy serves.
RUN apk add --no-cache python3 py3-flask py3-bcrypt py3-gunicorn py3-cryptography ca-certificates

# The same user id as the tools, because it writes to the account directory in
# MoClo's volume: a file it created as anyone else would lock them out.
RUN adduser -D -u 1000 portal && mkdir -p /suite && chown portal:portal /suite

COPY portal.py directory.py labs.py /srv/portal/
COPY pages /srv/portal/pages
WORKDIR /srv/portal
USER portal

ENV MOCLO_DB=/moclo/moclo.db \
    EDITOR_DB=/data/plasmid_editor.db \
    SUITE_DB=/suite/suite.db \
    URL_PREFIX=/account

EXPOSE 5003
# 127.0.0.1, not localhost: in Alpine localhost is IPv6 (::1) first, and
# gunicorn listens on IPv4 only.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:5003/health > /dev/null || exit 1

# Every request to a tool waits on /api/check, so threads keep a slow
# sign-in (bcrypt is deliberately slow) from holding everyone else up.
CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "1", "--threads", "8", "portal:app"]
