#!/usr/bin/env bash
# Redeploy chd-ds-token-issuer WITHOUT storage-account keys.
#
# deploy.sh uploads the package to the Function's own storage account and needs
# `listKeys` there, which the standing team role does not have (AuthorizationFailed).
# This variant builds the SAME vendored package and ships it through the publishing
# channel (`config-zip`), which Website Contributor on the resource group allows.
# On Linux Consumption, config-zip stores the zip in the app's `function-releases`
# container and points WEBSITE_RUN_FROM_PACKAGE at it itself. The script's warning
# about config-zip skipping pip does not bite: the zip already vendors its deps.
# Documented and verified in the team KB (infrastructure/token-issuer.md, 2026-07-30,
# used to register `regional-forecasts`).
#
# Prerequisites: az logged into OCHA-PROD (`az account set --subscription 3767353a-…`),
# uv. Run from the token-issuer/ dir: ./deploy-zip.sh
set -euo pipefail
RG="${RG:-IMB-CHD-DataScience-EastUS2}"
APP="${APP:-chd-ds-token-issuer}"
PYVER="3.11"
PLATFORM="x86_64-manylinux2014"      # Azure Functions Linux is manylinux-compatible

here="$(cd "$(dirname "$0")" && pwd)"
build="$(mktemp -d)"; trap 'rm -rf "$build"' EXIT
pkg="$build/pkg"; mkdir -p "$pkg/.python_packages/lib/site-packages"

echo "==> copy source"
cp "$here/host.json" "$here/requirements.txt" "$here/function_app.py" "$pkg/"

echo "==> vendor Linux deps ($PLATFORM, py$PYVER)"
uv pip install --target "$pkg/.python_packages/lib/site-packages" \
  --python-platform "$PLATFORM" --python-version "$PYVER" \
  -r "$here/requirements.txt" >/dev/null

echo "==> zip package (code + deps at root)"
zip="$build/token-issuer.zip"
( cd "$pkg" && zip -rq "$zip" . -x '*.pyc' '*/__pycache__/*' )

echo "==> previous WEBSITE_RUN_FROM_PACKAGE (for rollback: set it back and restart)"
az functionapp config appsettings list -g "$RG" -n "$APP" \
  --query "[?name=='WEBSITE_RUN_FROM_PACKAGE'].value" -o tsv | sed 's/sig=[^&]*/sig=<redacted>/'

echo "==> config-zip deploy"
az functionapp deployment source config-zip -g "$RG" -n "$APP" --src "$zip" --timeout 600 -o table

echo "==> done. verify (allow ~1 min for restart); every line must say delegation-platinum:"
for q in "satellite-viewer&tier=prod" "regional-forecasts&tier=assets" "cems-flood-labels&tier=platinum" "flood-labels&tier=platinum"; do
  echo "    curl -s 'https://$APP.azurewebsites.net/api/token?app=$q' | jq -c '{mode, platinum_dir}'"
done
