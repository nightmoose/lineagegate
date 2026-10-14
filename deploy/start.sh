#!/bin/sh
# Start FalkorDB locally, seed the graph if empty (self-healing), then serve the API/UI.
set -e
DATA=${FALKORDB_DATA_PATH:-/var/lib/falkordb/data}
mkdir -p "$DATA"
redis-server --bind 127.0.0.1 --port 6379 --dir "$DATA" --save 60 1 --appendonly no \
  --loadmodule /var/lib/falkordb/bin/falkordb.so $FALKORDB_ARGS &
for i in $(seq 1 50); do redis-cli -p 6379 ping >/dev/null 2>&1 && break; sleep 0.2; done
/app/.venv/bin/python -m lineagegate.seed.ensure
exec /app/.venv/bin/uvicorn lineagegate.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"
