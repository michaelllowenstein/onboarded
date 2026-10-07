-- Ticket 1001 | FIX — ships with ROLLBACK active.
-- To apply for real: change the last line to COMMIT;, then
--   ob-dba run 1001 fix --sandbox --yes   (rehearse on a throwaway copy)
--   ob-dba run 1001 fix --yes             (live)
BEGIN;

-- Guard: refuse if P-1002 is not in the broken state any more.
DO $$
BEGIN
    IF (SELECT count(*) FROM demo.policy_version v JOIN demo.policy p USING (policy_id)
        WHERE p.policy_number = 'P-1002' AND v.is_current) <> 0 THEN
        RAISE EXCEPTION 'Guard: P-1002 already has a current version — nothing to fix.';
    END IF;
END $$;

UPDATE demo.policy_version SET is_current = true, updated_at = now()
WHERE  policy_version_id = (
    SELECT v.policy_version_id FROM demo.policy_version v JOIN demo.policy p USING (policy_id)
    WHERE  p.policy_number = 'P-1002' ORDER BY v.version_number DESC LIMIT 1);

-- Verify inside the transaction; any failure aborts before COMMIT.
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM demo.policy_version v JOIN demo.policy p USING (policy_id)
    WHERE p.policy_number = 'P-1002' AND v.is_current;
    IF n <> 1 THEN RAISE EXCEPTION 'Verify: expected 1 current version, found %', n; END IF;
    RAISE NOTICE 'Verify OK: P-1002 has exactly one current version.';
END $$;

ROLLBACK;  -- COMMIT;
