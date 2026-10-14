-- Ticket {{TICKET_ID}} | ROLLBACK — restores dryrun RS1 values.
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}} | Author: {{AUTHOR_NAME}}
BEGIN;
-- UPDATE {{TARGET_TABLE}} SET <col> = <literal from RS1> WHERE ...;
ROLLBACK;  -- COMMIT;
