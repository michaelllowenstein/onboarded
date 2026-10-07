# Ticket {{TICKET_ID}}

**Cluster:** {{CLUSTER}}
**Target table:** {{TARGET_TABLE}}
**Author:** {{AUTHOR_NAME}}

| File | Purpose |
|---|---|
| diagnostic.sql | Read-only: confirms the data matches the cluster pattern |
| dryrun.sql | Full fix inside BEGIN … ROLLBACK, ends with a PASS/FAIL gate table |
| fix.sql | Ships with `ROLLBACK;  -- COMMIT;` — flip only after every dryrun gate passes |
| rollback.sql | Restores the dryrun RS1 values |

Checklist
- [ ] diagnostic confirms the pattern
- [ ] dryrun gates all PASS
- [ ] `ob-dba run {{TICKET_ID}} fix --sandbox --yes` clean
- [ ] rollback.sql populated from dryrun RS1
- [ ] fix.sql / rollback.sql back to `ROLLBACK;  -- COMMIT;` before committing to git
