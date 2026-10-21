#!/bin/bash
# Local PostgreSQL for the WSL build node, mirroring proximal's layout that
# engram/hippo tests assume: peer-auth socket at /var/run/postgresql, role
# `halbritt` with CREATEDB, databases engram / engram_test / hippo, pgvector +
# pgcrypto available. Idempotent; run as halbritt over `ssh peecee-wsl`.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
S="sudo -n"
$S apt-get install -y -q postgresql postgresql-contrib
PGMAJOR="$(ls /usr/lib/postgresql | sort -n | tail -1)"
$S apt-get install -y -q "postgresql-${PGMAJOR}-pgvector"
$S systemctl enable --now postgresql
$S -u postgres psql -Atc "select 1 from pg_roles where rolname='halbritt'" | grep -q 1 || \
  $S -u postgres createuser --createdb --createrole halbritt
for db in engram engram_test hippo; do
  $S -u postgres psql -Atc "select 1 from pg_database where datname='$db'" | grep -q 1 || \
    $S -u postgres createdb -O halbritt "$db"
  # extensions need superuser; pre-create so migrations' CREATE EXTENSION IF NOT EXISTS is a no-op
  $S -u postgres psql -q -d "$db" -c "create extension if not exists vector; create extension if not exists pgcrypto;"
done
psql -At -d engram -c "select current_user, version()" | cut -c1-60
psql -At -d engram -c "select extname from pg_extension" | tr '\n' ' '; echo
