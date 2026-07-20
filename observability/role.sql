-- Exporter login role for the proximal observability stack (postgres_exporter).
-- Run as a superuser: sudo -u postgres psql -f role.sql  (after substituting the password).
--
-- The PASSWORD is NOT stored in this repo. Generate one (e.g. `openssl rand -hex 24`), set it
-- here transiently or via \set, and put the resulting DSN ONLY in the root-only 0600
-- EnvironmentFile /etc/default/prometheus-postgres-exporter (see exporter/ template).
--
-- The role is deliberately minimal: a LOGIN role that inherits the existing read-only
-- capability role proximal_monitor (member of pg_monitor) — so it can read all pg_stat_*,
-- pg_read_all_settings, pg_read_all_stats (incl. other roles' query text in
-- pg_stat_statements) but holds no write/DDL/superuser rights of its own.

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter') THEN
    CREATE ROLE postgres_exporter LOGIN;
  END IF;
END $$;

-- Set the generated scram password (PG17 default password_encryption=scram-sha-256):
ALTER ROLE postgres_exporter WITH LOGIN CONNECTION LIMIT 5 PASSWORD 'REDACTED_SET_FROM_GENERATED_SECRET';

GRANT proximal_monitor TO postgres_exporter;            -- inherits pg_monitor
GRANT CONNECT ON DATABASE striatum_daemon TO postgres_exporter;

-- gpu-fleet registry metrics (PROXIMAL-5): the SECOND exporter instance (:9188, see
-- exporter/prometheus-postgres-exporter-gpufleet.*) connects to gpu_fleet with this same
-- role. pg_monitor does NOT grant SELECT on user tables, so the fleet tables/views need
-- explicit read grants — run this block IN the gpu_fleet database, as its owner (halbritt):
--   psql -d gpu_fleet -c "GRANT CONNECT ON DATABASE gpu_fleet TO postgres_exporter;"
--   psql -d gpu_fleet -c "GRANT SELECT ON gpu_slots, live_slots, routable_slots TO postgres_exporter;"

-- Verify (expects: 1 | t | t):
--   SELECT 1,
--          pg_has_role('postgres_exporter','pg_monitor','USAGE'),
--          (SELECT count(*) > 0 FROM pg_stat_statements LIMIT 1);

-- Revert:
--   DROP ROLE postgres_exporter;
