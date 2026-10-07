# Ticket 1001 — P-1002 has no current policy_version

Rehearsal ticket for the generic tenant. Data comes from
`deploy/local/db/sql/20_demo_schema.sql` (database `ob_generic`).

1. `onboarded dba run 1001 diagnostic` — Q1 lists P-1002 with current_versions = 0
2. `onboarded dba run 1001 dryrun` — RS4 gates all PASS; database unchanged
3. Change the last line of fix.sql to `COMMIT;`
4. `onboarded dba run 1001 fix --sandbox --yes` — runs on a throwaway copy, NOTICE "Verify OK"
5. `onboarded dba run 1001 fix --yes` — live
6. `onboarded dba run 1001 diagnostic` — Q1 now returns no rows
7. Undo: last line of rollback.sql → `COMMIT;`, then `onboarded dba run 1001 rollback --yes`
8. Put both files back to `ROLLBACK;  -- COMMIT;` before committing them to git
