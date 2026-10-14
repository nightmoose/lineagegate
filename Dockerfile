# Single image: FalkorDB (redis-server + graph module) + LineageGate API/UI.
FROM falkordb/falkordb:latest
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data ./data
RUN python3 -m venv /app/.venv && /app/.venv/bin/pip install --no-cache-dir -e '.[llm,api]'
COPY deploy/start.sh /app/start.sh
ENV FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 LINEAGEGATE_GRAPH=acme PORT=8080
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
