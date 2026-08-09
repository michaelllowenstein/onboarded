# ADO #{{TICKET_ID}} — Phalanx Package

**Cluster:** {{CLUSTER}}
**Target table:** {{TARGET_TABLE}}
**Fix mechanism:** {{FIX_MECHANISM}}
**Author:** {{AUTHOR_LOGIN}}
**PartyID:** {{AUTHOR_PARTY_ID}}

## Files

| File | Purpose |
|---|---|
| diagnostic.sql | Confirms data state matches cluster pattern |
| dryrun-{{TICKET_ID}}.sql | Full fix path inside ROLLBACK — produces RS5 gate table |
| fix.sql | Production fix — run only after 5/5 gates pass in dryrun |
| rollback.sql | Reverses the fix using literal prior values from dryrun RS1 |

## Pre-submission checklist

- [ ] Diagnostic confirms cluster pattern
- [ ] Dryrun RS5 shows 5/5 PASS
- [ ] Rollback tokens populated from dryrun RS1
- [ ] Redgate Prompt lint (Ctrl+K+Y) passed on all .sql files
- [ ] CC Jackie Broyer on submission email to {{SUBMISSION_EMAIL}}