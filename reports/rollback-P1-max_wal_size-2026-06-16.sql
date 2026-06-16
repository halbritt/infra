-- Rollback bundle for P1 (max_wal_size 1GB -> 16GB), staged 2026-06-16.
-- Plan: reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md
-- Run as superuser:  sudo -u postgres psql -d postgres -f reports/rollback-P1-max_wal_size-2026-06-16.sql
--
-- Reverts to the captured prior value (source = configuration file, '1GB') via an
-- explicit SET, not a blind RESET. Guard refuses to fire unless live state is the
-- post-change value, so it won't clobber an out-of-band change.

DO $$
BEGIN
  IF current_setting('max_wal_size') <> '16GB' THEN
    RAISE EXCEPTION
      'live max_wal_size=% (expected 16GB post-change) -- refusing blind revert; investigate drift',
      current_setting('max_wal_size');
  END IF;
END $$;

ALTER SYSTEM SET max_wal_size = '1GB';
SELECT pg_reload_conf();

-- confirm:
SELECT name, setting, unit, pending_restart FROM pg_settings WHERE name = 'max_wal_size';
