-- Ticket {{TICKET_ID}} | DRY RUN — last line is always ROLLBACK.
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}} | Author: {{AUTHOR_NAME}}
BEGIN;

-- RS1: pre-fix state (copy literal values into rollback.sql)
-- CREATE TEMP TABLE t_before ON COMMIT DROP AS SELECT ... FROM {{TARGET_TABLE}} WHERE ...;
-- SELECT * FROM t_before;

-- Simulated fix
-- UPDATE {{TARGET_TABLE}} SET ... WHERE ...;

-- RS2: post-fix state
-- SELECT ... FROM {{TARGET_TABLE}} WHERE ...;

-- RS3: gate table — every row must be PASS
-- SELECT gate, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result
-- FROM (VALUES ('1 ...', <condition>), ('2 ...', <condition>)) g(gate, ok);

ROLLBACK;
