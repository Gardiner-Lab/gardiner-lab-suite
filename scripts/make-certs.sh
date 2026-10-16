#!/usr/bin/env bash
# The certificates the suite is served over https with: a certificate
# authority of the lab's own, and a certificate for this machine signed by it.
#
#   ./scripts/make-certs.sh          make them, or renew the machine's (install.sh runs this)
#   ./scripts/make-certs.sh --force  make the machine's certificate again now
#
# Browsers do not know the lab's authority, so each computer trusts it once:
# download it from https://<this machine>:<port>/lab-suite-ca.crt and follow
# docs/HTTPS.md. Trusted once, it stays trusted: the machine's certificate can
# be renewed, or made for new names, without anyone trusting anything again.
#
#   certs/suite.crt, suite.key   this machine's certificate, which the proxy serves
#   certs/lab-suite-ca.crt       the authority's certificate, for computers to trust
#   certs-ca/lab-suite-ca.key    the authority's own key: never leaves this machine,
#                                and the proxy never sees it. Keep a copy somewhere
#                                safe: without it, a new authority means every
#                                computer trusts again.
#
# The certificate names localhost, this machine's name (short and full), and
# whatever SUITE_HOSTNAMES in .env adds (comma-separated names or addresses:
# the machine's IP address, say, or the name UU's DNS gives it).
#
# A certificate from the university instead: put it and its key in
# certs/suite.crt and certs/suite.key, and touch certs/.provided so this script
# leaves them alone.
set -euo pipefail
cd "$(dirname "$0")/.."
# Git Bash would otherwise read /CN=... as a path.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

CERTS=certs
CA_DIR=certs-ca
mkdir -p "$CERTS" "$CA_DIR"
chmod 700 "$CA_DIR" 2>/dev/null || true

if [ -f "$CERTS/.provided" ]; then
    echo "certs/.provided: using the certificate put there, not making one"
    exit 0
fi

# openssl here, or in a throw-away container when this machine has none.
if command -v openssl >/dev/null 2>&1; then
    ossl() { openssl "$@"; }
else
    ossl() {
        docker run --rm -v "$(pwd -W 2>/dev/null || pwd):/w" -w /w alpine:3.20 \
            sh -c 'apk add -q --no-cache openssl >/dev/null && openssl "$@"' openssl "$@"
    }
fi

env_value() {
    [ -f .env ] || return 0
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env | tail -1 | tr -d "\r\"'"
}

# The names and addresses the certificate is for.
names=(localhost "$(hostname)")
full="$(hostname -f 2>/dev/null || true)"
[ -n "$full" ] && [ "$full" != "$(hostname)" ] && names+=("$full")
IFS=',' read -r -a extra <<< "$(env_value SUITE_HOSTNAMES)"
for n in "${extra[@]}"; do n="$(echo "$n" | tr -d ' ')"; [ -n "$n" ] && names+=("$n"); done
san="IP:127.0.0.1"
seen=" "
for n in "${names[@]}"; do
    low="$(echo "$n" | tr '[:upper:]' '[:lower:]')"
    case "$seen" in *" $low "*) continue ;; esac
    seen="$seen$low "
    if [[ "$low" =~ ^[0-9.]+$ || "$low" == *:* ]]; then san="$san,IP:$low"; else san="$san,DNS:$low"; fi
done

# A config of our own, not the system's: its defaults differ from machine to
# machine, and can add an extension a second time, which makes a certificate
# invalid.
config() {   # config FILE "common name" "extensions"
    printf '[req]\nprompt = no\ndistinguished_name = dn\nx509_extensions = ext\n[dn]\nO = Gardiner Lab suite\nCN = %s\n[ext]\n%s\n' \
        "$2" "$3" > "$1"
}

# --- the lab's authority: made once ---------------------------------------------
if [ ! -f "$CA_DIR/lab-suite-ca.key" ] || [ ! -f "$CERTS/lab-suite-ca.crt" ]; then
    echo "Making the lab's certificate authority (once)"
    config "$CA_DIR/ca.cnf" "Gardiner Lab suite authority ($(hostname))" \
        "$(printf 'basicConstraints = critical,CA:TRUE,pathlen:0\nkeyUsage = critical,keyCertSign,cRLSign\nsubjectKeyIdentifier = hash')"
    ossl req -x509 -new -newkey rsa:3072 -nodes -sha256 -days 3650 -config "$CA_DIR/ca.cnf" \
        -keyout "$CA_DIR/lab-suite-ca.key" -out "$CERTS/lab-suite-ca.crt" 2>/dev/null
    chmod 600 "$CA_DIR/lab-suite-ca.key" 2>/dev/null || true
    FORCE=1
fi

# --- this machine's certificate: made again when its names change or it nears its end
renew=$FORCE
[ -f "$CERTS/suite.crt" ] && [ -f "$CERTS/suite.key" ] || renew=1
[ "$(cat "$CERTS/.names" 2>/dev/null || true)" = "$san" ] || renew=1
if [ "$renew" = 0 ] && ! ossl x509 -checkend $((30 * 86400)) -noout -in "$CERTS/suite.crt" >/dev/null 2>&1; then
    renew=1
fi
if [ "$renew" = 0 ]; then
    echo "certs/suite.crt is current, for ${san//,/, }"
    exit 0
fi

echo "Making this machine's certificate, for ${san//,/, }"
ext="$CA_DIR/suite.ext"
cat > "$ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$san
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EOF
config "$CA_DIR/suite.cnf" "$(hostname)" "subjectKeyIdentifier = hash"
ossl req -new -newkey rsa:2048 -nodes -sha256 -config "$CA_DIR/suite.cnf" \
    -keyout "$CERTS/suite.key" -out "$CA_DIR/suite.csr" 2>/dev/null
# 825 days: the longest Apple's systems accept for a server's certificate.
ossl x509 -req -sha256 -days 825 -in "$CA_DIR/suite.csr" -CA "$CERTS/lab-suite-ca.crt" \
    -CAkey "$CA_DIR/lab-suite-ca.key" -CAcreateserial -CAserial "$CA_DIR/lab-suite-ca.srl" \
    -extfile "$ext" -out "$CERTS/suite.crt" 2>/dev/null
rm -f "$CA_DIR/suite.csr"
# The proxy (nginx, running as root to read it) needs the key; nobody else does.
chmod 600 "$CERTS/suite.key" 2>/dev/null || true
printf '%s' "$san" > "$CERTS/.names"
echo "Done. Restart the proxy to use it: docker compose restart proxy"
