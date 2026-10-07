-- Ticket 1001 | Diagnostic (read only — safe as ob_reader)
-- Symptom: "Sequence contains no elements" loading policy P-1002
-- Hypothesis: no demo.policy_version row has is_current = true

-- Q0: schema probe
SELECT column_name, data_type, is_nullable
FROM   information_schema.columns
WHERE  table_schema = 'demo' AND table_name = 'policy_version'
ORDER  BY ordinal_position;

-- Q1: every policy whose current-version count is not exactly 1
SELECT p.policy_id, p.policy_number,
       count(*) FILTER (WHERE v.is_current) AS current_versions,
       count(*)                             AS total_versions,
       max(v.version_number)                AS latest_version
FROM   demo.policy p
JOIN   demo.policy_version v USING (policy_id)
GROUP  BY p.policy_id, p.policy_number
HAVING count(*) FILTER (WHERE v.is_current) <> 1
ORDER  BY p.policy_id;
