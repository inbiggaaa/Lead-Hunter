#!/bin/bash
# Quick restart with cache clear
cd /opt/LeadHunter
docker compose stop bot
docker compose exec bot sh -c "find /app -name '__pycache__' -exec rm -rf {} + 2>/dev/null; find /app -name '*.pyc' -delete 2>/dev/null"
docker compose up -d bot
echo "✅ Bot restarted with clean cache"
