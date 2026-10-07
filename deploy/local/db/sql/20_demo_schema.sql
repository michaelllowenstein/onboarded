-- ─────────────────────────────────────────────────────────────────────────
-- 20_demo_schema.sql — tiny neutral dataset for rehearsing a full ticket
-- cycle (diagnostic → dryrun → fix → rollback) on the generic tenant.
-- P-1002 is deliberately broken: it has NO current version.
-- Run as ob_dba against the generic instance database. Re-runnable.
-- ─────────────────────────────────────────────────────────────────────────
\set ON_ERROR_STOP on
BEGIN;
CREATE SCHEMA IF NOT EXISTS demo;
DROP TABLE IF EXISTS demo.policy_version, demo.policy;

CREATE TABLE demo.policy (
    policy_id     int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_number text        NOT NULL UNIQUE,
    status_code   smallint    NOT NULL,          -- 1 quoted, 2 bound, 3 cancelled
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE demo.policy_version (
    policy_version_id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_id         int           NOT NULL REFERENCES demo.policy(policy_id),
    version_number    smallint      NOT NULL,
    is_current        boolean       NOT NULL,
    premium           numeric(12,2) NOT NULL,
    updated_at        timestamptz
);
INSERT INTO demo.policy (policy_number, status_code) VALUES ('P-1001', 2), ('P-1002', 2), ('P-1003', 1);
INSERT INTO demo.policy_version (policy_id, version_number, is_current, premium) VALUES
    (1, 1, false, 812.00), (1, 2, true, 845.50),
    (2, 1, false, 640.00), (2, 2, false, 655.25),     -- broken: no current version
    (3, 1, true,  410.00);
COMMIT;
\echo Demo schema seeded (P-1002 intentionally broken).
