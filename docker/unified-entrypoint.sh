#!/bin/sh
set -eu

SECRETS_DIR="${SINAPSE_SECRETS_DIR:-/run/sinapse}"

if [ -z "${DATABASE_PASS:-}" ] && [ -r "$SECRETS_DIR/database_pass" ]; then
  DATABASE_PASS="$(cat "$SECRETS_DIR/database_pass")"
  export DATABASE_PASS
fi

if [ -z "${ENCRYPTION_KEY:-}" ] && [ -r "$SECRETS_DIR/encryption_key" ]; then
  ENCRYPTION_KEY="$(cat "$SECRETS_DIR/encryption_key")"
  export ENCRYPTION_KEY
fi

if [ -z "${GF_SECURITY_ADMIN_PASSWORD:-}" ] && [ -r "$SECRETS_DIR/grafana_admin_password" ]; then
  GF_SECURITY_ADMIN_PASSWORD="$(cat "$SECRETS_DIR/grafana_admin_password")"
  export GF_SECURITY_ADMIN_PASSWORD
fi

case "${SINAPSE_SERVICE:-teslamate}" in
  teslamate)
    : "${DATABASE_PASS:?DATABASE_PASS is missing and no generated secret was found}"
    : "${ENCRYPTION_KEY:?ENCRYPTION_KEY is missing and no generated secret was found}"
    export HOME=/opt/app
    export SRTM_CACHE=${SRTM_CACHE:-/opt/app/.srtm_cache}
    cd /opt/app
    exec tini -- /bin/dash /teslamate-entrypoint.sh bin/teslamate start
    ;;
  grafana)
    : "${DATABASE_PASS:?DATABASE_PASS is missing and no generated secret was found}"
    : "${GF_SECURITY_ADMIN_PASSWORD:?Grafana admin password is missing and no generated secret was found}"
    export HOME=${HOME:-/usr/share/grafana}
    exec /run.sh
    ;;
  *)
    echo "Unknown SINAPSE_SERVICE: ${SINAPSE_SERVICE}. Use teslamate or grafana." >&2
    exit 64
    ;;
esac
