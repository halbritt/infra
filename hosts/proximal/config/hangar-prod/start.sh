#!/usr/bin/env bash
set -euo pipefail
cd /home/halbritt/services/hangar-prod
compose=(docker compose --env-file hangar.env)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --pull never plane-db plane-redis plane-mq plane-minio
# One migration runner, completed before applications start. The migration profile
# excludes this service from the following ordinary up command.
"${compose[@]}" run --rm --no-deps migrator
"${compose[@]}" up -d --pull never
