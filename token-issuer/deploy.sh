#!/usr/bin/env bash
# Deploy / redeploy chd-ds-token-issuer.
#
# Why this script exists: `func` Core Tools aren't assumed installed, and on Linux
# Consumption `az functionapp deployment source config-zip` silently uses run-from-package
# (skips pip) while OneDeploy is disabled in this environment. So we VENDOR the Linux wheels
# into the package ourselves and point WEBSITE_RUN_FROM_PACKAGE at it directly.
#
# Prereqisites: az (logged into OCHA-PROD), uv. Run from the token-issuer/ dir: ./deploy.sh
set -euo pipefail

RG="${RG:-IMB-CHD-DataScience-EastUS2}"
APP="${APP:-chd-ds-token-issuer}"
SA="${SA:-chd0tokenissuer}"          # the Function's own runtime storage account
CONTAINER="deploy"
BLOB="token-issuer.zip"
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
zip="$build/$BLOB"
( cd "$pkg" && zip -rq "$zip" . -x '*.pyc' '*/__pycache__/*' )

echo "==> upload package to $SA/$CONTAINER/$BLOB"
KEY="$(az storage account keys list -n "$SA" -g "$RG" --query '[0].value' -o tsv)"
az storage container create --account-name "$SA" --account-key "$KEY" --name "$CONTAINER" -o none
az storage blob upload --account-name "$SA" --account-key "$KEY" \
  --container-name "$CONTAINER" --name "$BLOB" --file "$zip" --overwrite -o none

echo "==> point app at package (fresh SAS busts the run-from-package cache) + restart"
URL="$(az storage blob generate-sas --account-name "$SA" --account-key "$KEY" \
  --container-name "$CONTAINER" --name "$BLOB" --permissions r \
  --expiry 2030-01-01T00:00Z --https-only --full-uri -o tsv)"
az functionapp config appsettings set -g "$RG" -n "$APP" \
  --settings WEBSITE_RUN_FROM_PACKAGE="$URL" -o none
az functionapp restart -g "$RG" -n "$APP"

echo "==> done. verify (allow ~1 min for restart):"
echo "    curl -s https://$APP.azurewebsites.net/api/token | jq '{mode,platinum_dir,expires}'"
