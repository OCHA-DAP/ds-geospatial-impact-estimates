#!/usr/bin/env bash
# Deploy the viewer to Azure App Service (blue-green via a staging slot).
#
#   scripts/deploy.sh            build the SPA + locked deps, deploy to STAGING
#   scripts/deploy.sh swap       promote: swap staging -> production
#   scripts/deploy.sh rollback   undo: swap back (production <-> staging again)
#
# Prereqs: `az login` as the UN account (adm.zarno1@global.un.org), `uv` and a
# `cd web && npm install` done once. No secrets are handled here — the SAS lives
# in the app's slot settings already.
set -euo pipefail

RG=IMB-CHD-DataScience-EastUS2
APP=chd-ds-geospatial-impact-viewer
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

swap() {
  echo "==> Swapping staging <-> production (zero-downtime)"
  az webapp deployment slot swap -g "$RG" -n "$APP" --slot staging --target-slot production
  echo "==> Production: https://${APP}.azurewebsites.net"
}

case "${1:-deploy}" in
  deploy)
    echo "==> Building SPA"
    ( cd web && npm run build )
    echo "==> Regenerating locked requirements.txt from uv.lock"
    uv export --no-dev --group api --no-emit-project --no-hashes -o requirements.txt
    echo "==> Zipping deploy artifact"
    ZIP="$(mktemp -d)/deploy.zip"
    zip -r -q "$ZIP" api src web/dist requirements.txt asgi.py -x '*__pycache__*' -x '*.pyc'
    echo "==> Deploying to staging slot"
    az webapp deploy -g "$RG" -n "$APP" --slot staging --src-path "$ZIP" --type zip
    echo "==> Test it: https://${APP}-staging.azurewebsites.net"
    echo "    Then promote with: scripts/deploy.sh swap"
    ;;
  swap)     swap ;;
  rollback) echo "(rollback is just another swap)"; swap ;;
  *) echo "usage: scripts/deploy.sh [deploy|swap|rollback]" >&2; exit 1 ;;
esac
