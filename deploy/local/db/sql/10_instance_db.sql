-- ─────────────────────────────────────────────────────────────────────────
-- 10_instance_db.sql — one database per onboarded instance. Idempotent.
--   psql -d postgres -v db_name=ob_<slug> -f 10_instance_db.sql
-- Creates the database (owner ob_dba), the err.db_exception_tank the DBA
-- runner logs failures to, and read-only grants for ob_reader that also
-- cover tables created later (restored dumps, migrations).
-- ─────────────────────────────────────────────────────────────────────────
\set ON_ERROR_STOP on
SELECT format('CREATE DATABASE %I OWNER ob_dba', :'db_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db_name') \gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO ob_reader', :'db_name') \gexec

\connect :"db_name"
SET ROLE ob_dba;     -- objects below are owned by ob_dba, so its default privileges apply

CREATE SCHEMA IF NOT EXISTS err;
CREATE TABLE IF NOT EXISTS err.db_exception_tank (
    exception_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    database_name  text,
    user_name      text,
    code_author    text,
    sqlstate       char(5),
    error_message  text,
    script_label   text,
    batch_index    int,
    logged_at      timestamptz NOT NULL DEFAULT now()
);
GRANT USAGE ON SCHEMA err TO ob_reader;
GRANT SELECT, INSERT ON err.db_exception_tank TO ob_reader;

-- Read-only access to everything ob_dba creates from now on, in any schema.
ALTER DEFAULT PRIVILEGES FOR ROLE ob_dba GRANT SELECT ON TABLES    TO ob_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ob_dba GRANT SELECT ON SEQUENCES TO ob_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ob_dba GRANT USAGE  ON SCHEMAS   TO ob_reader;
GRANT USAGE ON SCHEMA public TO ob_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ob_reader;
RESET ROLE;
\echo Instance database :db_name ready.
