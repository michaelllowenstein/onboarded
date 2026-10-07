-- ─────────────────────────────────────────────────────────────────────────
-- 00_roles.sql — cluster-level roles. Run once per server, as postgres. Idempotent.
--   psql -v dba_password=... -v reader_password=... -f 00_roles.sql
-- ob_dba     owns every instance database; runs tickets; may CREATEDB
--            (needed for --sandbox clones).
-- ob_reader  read-only, mirrors a production read replica.
-- ─────────────────────────────────────────────────────────────────────────
\set ON_ERROR_STOP on
SELECT 'CREATE ROLE ob_dba LOGIN CREATEDB'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ob_dba') \gexec
SELECT 'CREATE ROLE ob_reader LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ob_reader') \gexec
ALTER ROLE ob_dba    WITH LOGIN CREATEDB PASSWORD :'dba_password';
ALTER ROLE ob_reader WITH LOGIN PASSWORD :'reader_password';
