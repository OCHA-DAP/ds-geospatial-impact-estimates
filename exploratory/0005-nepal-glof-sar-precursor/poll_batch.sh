#!/bin/zsh
# Poll the GEE batch pipeline every 15 min until phase C has collected the
# tier-1 table, then exit (the session is notified and finishes the build).
cd "$(dirname "$0")"
for i in {1..40}; do
  if [ -s data/himalaya_tier1.csv ]; then
    echo "collected after $i polls"
    exit 0
  fi
  uv run --group etl --with earthengine-api,geopandas python himalaya_batch.py 2>&1 | tail -3
  [ -s data/himalaya_tier1.csv ] && { echo "collected"; exit 0; }
  sleep 900
done
echo "gave up after 40 polls (~10 h)"
exit 1
