#!/bin/sh
# Makes the certificates of the https address before nginx starts (nginx's image runs every script of
# /docker-entrypoint.d/ first). Both are kept in the /certs volume:
#   ca.crt, ca.key          a small certificate authority of our own, made once and valid for ten years
#   server.crt, server.key  the certificate of the site, signed by that authority, for localhost, 127.0.0.1 and every
#                           address or name in HTTPS_HOSTS. It is made again when that list changes or it is about to expire.
# A device that installs ca.crt once (nginx offers it at /local-ca.crt) stops showing the certificate warning, and the
# site certificate can be renewed or changed later without installing anything again. ca.key never leaves the volume.
set -eu

DIR=/certs
CA_DAYS=3650
SERVER_DAYS=825
RENEW_WITHIN_DAYS="${HTTPS_RENEW_WITHIN_DAYS:-30}"

log() { echo "[https] $*"; }

mkdir -p "$DIR"
cd "$DIR"

# ---- the certificate authority ----
if [ ! -s ca.key ] || [ ! -s ca.crt ]; then
    log "making the local certificate authority (valid $CA_DAYS days)"
    rm -f ca.key ca.crt ca.srl server.key server.crt hosts.txt
    cat > ca.cnf <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no
[dn]
O = Learn English
CN = Learn English local CA
[v3_ca]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
    openssl genrsa -out ca.key 2048 2>/dev/null
    openssl req -x509 -new -key ca.key -sha256 -days "$CA_DAYS" -config ca.cnf -out ca.crt
    rm -f ca.cnf
    chmod 600 ca.key
fi

# ---- the names the site certificate is for: localhost, 127.0.0.1 and everything in HTTPS_HOSTS ----
hosts=$(printf '%s\n' "localhost,127.0.0.1,${HTTPS_HOSTS:-}" | tr ',; ' '\n\n\n' | tr 'A-Z' 'a-z' | sed '/^$/d' | sort -u)
san=""
for host in $hosts; do
    case "$host" in
        *[!a-z0-9.:_-]*)
            log "skipping '$host': it is not a plain name or address"
            continue ;;
    esac
    if printf '%s\n' "$host" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
        entry="IP:$host"
    elif printf '%s\n' "$host" | grep -Eq '^[0-9a-f]*:[0-9a-f:]+$'; then
        entry="IP:$host"
    else
        entry="DNS:$host"
    fi
    san="${san:+$san,}$entry"
done

# ---- the site certificate ----
why=""
if [ ! -s server.crt ] || [ ! -s server.key ]; then
    why="there is none yet"
elif [ "$(cat hosts.txt 2>/dev/null || true)" != "$san" ]; then
    why="the list of addresses changed"
elif ! openssl verify -CAfile ca.crt server.crt >/dev/null 2>&1; then
    why="it is not signed by this authority"
elif ! openssl x509 -checkend $((RENEW_WITHIN_DAYS * 86400)) -noout -in server.crt >/dev/null; then
    why="it expires soon"
fi

if [ -n "$why" ]; then
    log "making the site certificate ($why)"
    cat > server.cnf <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
O = Learn English
CN = Learn English local site
[v3_server]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
subjectAltName = $san
EOF
    openssl genrsa -out server.key 2048 2>/dev/null
    openssl req -new -key server.key -config server.cnf -out server.csr
    openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days "$SERVER_DAYS" -sha256 \
        -extfile server.cnf -extensions v3_server -out server.crt 2>/dev/null
    rm -f server.csr server.cnf
    chmod 600 server.key
    printf '%s' "$san" > hosts.txt
fi

log "site certificate for: $san"
log "valid until: $(openssl x509 -enddate -noout -in server.crt | cut -d= -f2)"
log "certificate authority: $(openssl x509 -fingerprint -sha256 -noout -in ca.crt)"
log "a device can install the authority from /local-ca.crt to stop seeing the certificate warning"
