#!/bin/sh
set -eu

case "${SINAPSE_SERVICE:-teslamate}" in
  teslamate)
    export HOME=/opt/app
    export SRTM_CACHE=${SRTM_CACHE:-/opt/app/.srtm_cache}
    cd /opt/app
    exec tini -- /bin/dash /teslamate-entrypoint.sh bin/teslamate start
    ;;
  grafana)
    export HOME=${HOME:-/usr/share/grafana}
    exec /run.sh
    ;;
  *)
    echo "Unknown SINAPSE_SERVICE: ${SINAPSE_SERVICE}. Use teslamate or grafana." >&2
    exit 64
    ;;
esac
