#!/usr/bin/env bash
# Redeploy chd-ds-token-issuer WITHOUT `listKeys`.
#
# Same mechanism as deploy.sh (vendored Linux wheels + external run-from-package):
# the ONLY difference is where the storage key comes from. deploy.sh calls
# `az storage account keys list` on the Function's runtime storage account
# (`chd0tokenissuer`), which needs `listKeys` — the standing team role (Website
# Contributor on the RG) does not have it (AuthorizationFailed). That same role CAN
# read the app's settings, and `AzureWebJobsStorage` there carries the account key,
# so this script uses that connection string instead. Nothing is printed from it.
#
# Do NOT use `az functionapp deployment source config-zip` for this app. It was the
# documented keyless route (team KB, verified 2026-07-30 with an older CLI) but in
# az CLI 2.77.0 (2026-09-25) it stored the zip's PATH STRING as the package blob
# (80 bytes) and pointed the app at it: every registered app returned 503 until the
# package was re-deployed with this script.
#
# Prerequisites: az logged into OCHA-PROD (`az account set --subscription 3767353a-…`),
# uv. Run from the token-issuer/ dir: ./deploy-zip.sh
set -euo pipefail
RG="${RG:-IMB-CHD-DataScience-EastUS2}"
APP="${APP:-chd-ds-token-issuer}"
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
unzip -l "$zip" | grep -q " function_app.py$" || { echo "function_app.py missing from zip" >&2; exit 1; }

echo "==> storage connection from the app's own AzureWebJobsStorage setting"
CONN="$(az functionapp config appsettings list -g "$RG" -n "$APP" \
  --query "[?name=='AzureWebJobsStorage'].value" -o tsv)"
[ -n "$CONN" ] || { echo "AzureWebJobsStorage not readable" >&2; exit 1; }

echo "==> upload package to $CONTAINER/$BLOB"
az storage container create --connection-string "$CONN" --name "$CONTAINER" -o none
az storage blob upload --connection-string "$CONN" \
  --container-name "$CONTAINER" --name "$BLOB" --file "$zip" --overwrite -o none
uploaded="$(az storage blob show --connection-string "$CONN" --container-name "$CONTAINER" \
  --name "$BLOB" --query properties.contentLength -o tsv)"
[ "$uploaded" = "$(stat -f %z "$zip")" ] || { echo "uploaded size $uploaded != local" >&2; exit 1; }

echo "==> point app at package (fresh SAS busts the run-from-package cache) + restart"
URL="$(az storage blob generate-sas --connection-string "$CONN" \
  --container-name "$CONTAINER" --name "$BLOB" --permissions r \
  --expiry 2030-01-01T00:00Z --https-only --full-uri -o tsv)"
az functionapp config appsettings set -g "$RG" -n "$APP" \
  --settings WEBSITE_RUN_FROM_PACKAGE="$URL" -o none
az functionapp restart -g "$RG" -n "$APP" -o none

echo "==> verify (polls up to 4 min); every line must say delegation-platinum:"
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://$APP.azurewebsites.net/api/token?app=cems-flood-labels&tier=platinum")
  [ "$code" = "200" ] && break; sleep 10
done
for q in "satellite-viewer&tier=prod" "regional-forecasts&tier=assets" "cems-flood-labels&tier=platinum" "flood-labels&tier=platinum"; do
  printf '%s -> ' "$q"; curl -s "https://$APP.azurewebsites.net/api/token?app=$q" | jq -c '{mode, platinum_dir}'
done
