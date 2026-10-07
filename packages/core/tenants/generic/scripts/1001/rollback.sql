-- Ticket 1001 | ROLLBACK — restores the RS1 state from dryrun (no version current).
-- Same convention as fix.sql: change the last line to COMMIT; to apply.
BEGIN;
UPDATE demo.policy_version v SET is_current = false, updated_at = NULL
FROM   demo.policy p
WHERE  p.policy_id = v.policy_id AND p.policy_number = 'P-1002';
SELECT v.policy_version_id, v.version_number, v.is_current
FROM   demo.policy_version v JOIN demo.policy p USING (policy_id)
WHERE  p.policy_number = 'P-1002' ORDER BY v.version_number;
ROLLBACK;  -- COMMIT;
