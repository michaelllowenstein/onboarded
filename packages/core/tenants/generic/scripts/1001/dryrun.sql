-- Ticket 1001 | DRY RUN — always rolls back (last line is ROLLBACK, never COMMIT).
-- RS1 is the pre-fix state: copy it into rollback.sql if it ever differs.
BEGIN;

CREATE TEMP TABLE t_before ON COMMIT DROP AS
SELECT v.* FROM demo.policy_version v
JOIN demo.policy p USING (policy_id) WHERE p.policy_number = 'P-1002';

-- RS1: before
SELECT policy_version_id, version_number, is_current, updated_at FROM t_before ORDER BY version_number;

-- simulated fix: newest version becomes current
WITH target AS (
    SELECT policy_version_id FROM t_before ORDER BY version_number DESC LIMIT 1
), upd AS (
    UPDATE demo.policy_version v SET is_current = true, updated_at = now()
    FROM target WHERE v.policy_version_id = target.policy_version_id AND NOT v.is_current
    RETURNING v.policy_version_id
)
-- RS2: rows updated
SELECT count(*) AS rows_updated FROM upd;

-- RS3: after
SELECT v.policy_version_id, v.version_number, v.is_current, v.updated_at
FROM demo.policy_version v JOIN demo.policy p USING (policy_id)
WHERE p.policy_number = 'P-1002' ORDER BY v.version_number;

-- RS4: gates — every row must be PASS before fix.sql runs
WITH s AS (
    SELECT (SELECT count(*) FROM t_before)                                AS versions,
           (SELECT count(*) FROM t_before WHERE is_current)               AS before_current,
           (SELECT count(*) FROM demo.policy_version v JOIN demo.policy p USING (policy_id)
             WHERE p.policy_number = 'P-1002' AND v.is_current)           AS after_current
)
SELECT gate, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result
FROM s, LATERAL (VALUES
    ('1 policy has versions',       versions > 0),
    ('2 was broken (0 current)',    before_current = 0),
    ('3 exactly 1 current after',   after_current = 1)
) g(gate, ok);

ROLLBACK;
