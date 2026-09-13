#!/usr/bin/env bash
# Update the server after a push: align the clone with origin/main (the server never
# edits tracked files; judgments.csv and .env are ignored and survive), rebuild, restart,
# health check.
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch origin
git reset --hard origin/main
docker compose -f deploy/docker-compose.yml up -d --build
sleep 5
docker exec n8n-8zow-n8n-1 wget -qO- http://cv-service:8000/health && echo
