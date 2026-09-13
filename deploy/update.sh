#!/usr/bin/env bash
# Update cv-service on the server after a push: pull, rebuild, restart, health check.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose -f deploy/docker-compose.yml up -d --build
sleep 5
docker exec n8n-8zow-n8n-1 wget -qO- http://cv-service:8000/health && echo
