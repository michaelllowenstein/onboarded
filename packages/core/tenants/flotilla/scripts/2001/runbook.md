# Ticket 2001 — MR-STUCK-1 is Ongoing with no StartTime; Taurob-1 never frees up

Baseline v1 rehearsal ticket for the flotilla tenant. Data comes from
`benchmarks/baseline-v1/seed/` (database `ob_flotilla`).

**Code facts behind it** (flotilla@fdab8b1d):
`MissionRun.cs:36–38` sets `StartTime` when `Status` becomes `Ongoing`;
`MqttEventHandler.OnIsarMissionUpdate` (line 469) is the only writer of that transition;
`MissionSchedulingService.StartNextMissionRunIfSystemIsAvailable` (line 32) only starts
the next run when the robot is free (`Robot.IsStatusThatCanReceiveMissions`, line 90).

1. `onboarded dba run 2001 diagnostic`: Q1 lists MR-STUCK-1 with `robot_points_here = t`; Q2 lists MR-QUEUE-1
2. `onboarded dba run 2001 dryrun`: the RS3 gates all PASS; the database is unchanged
3. Change the last line of fix.sql to `COMMIT;`
4. `onboarded dba run 2001 fix --sandbox --yes`: runs on a throwaway copy and prints NOTICE "Verify OK"
5. `onboarded dba run 2001 fix --yes`: live
6. `onboarded dba run 2001 diagnostic`: Q1 now returns no rows
7. To undo: change the last line of rollback.sql to `COMMIT;`, then run `onboarded dba run 2001 rollback --yes`
8. Put both files back to `ROLLBACK;  -- COMMIT;` before committing them to git

In a real Flotilla deployment, make sure ISAR is not about to report this run before aborting it
(`isar/<id>/mission/<run>` on MQTT). Otherwise a late `OnIsarMissionUpdate` can move it back to Ongoing.
