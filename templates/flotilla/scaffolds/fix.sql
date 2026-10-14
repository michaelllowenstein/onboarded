-- Ticket {{TICKET_ID}} | FIX — ships with ROLLBACK active.
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}} | Author: {{AUTHOR_NAME}}
-- Apply: change the last line to COMMIT;, rehearse with --sandbox, then run with --yes.
BEGIN;

-- Guard: refuse if the data is no longer in the broken state
-- DO $$ BEGIN IF (<check>) THEN RAISE EXCEPTION 'Guard: ...'; END IF; END $$;

-- Change
-- UPDATE {{TARGET_TABLE}} SET ... WHERE ...;

-- Verify (raise to abort before COMMIT)
-- DO $$ BEGIN IF NOT (<check>) THEN RAISE EXCEPTION 'Verify: ...'; END IF; END $$;

ROLLBACK;  -- COMMIT;
