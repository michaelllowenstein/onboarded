-- Ticket 2001 | FIX — ships with ROLLBACK active.
-- To apply for real: change the last line to COMMIT;, then
--   onboarded dba run 2001 fix --sandbox --yes   (rehearse on a throwaway copy)
--   onboarded dba run 2001 fix --yes             (live)
-- Status strings are the EF enum names Flotilla stores (MissionStatus.Aborted, TaskStatus.Cancelled).
BEGIN;

-- Guard: refuse unless MR-STUCK-1 is still in the broken state.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."MissionRuns"
                   WHERE "Id" = 'MR-STUCK-1' AND "Status" = 'Ongoing' AND "StartTime" IS NULL) THEN
        RAISE EXCEPTION 'Guard: MR-STUCK-1 is not Ongoing-without-StartTime any more — nothing to fix.';
    END IF;
END $$;

UPDATE public."MissionRuns"
SET    "Status" = 'Aborted', "EndTime" = now(),
       "StatusReason" = 'Ticket 2001: Ongoing with no StartTime; aborted by DBA'
WHERE  "Id" = 'MR-STUCK-1';

UPDATE public."MissionTasks" SET "Status" = 'Cancelled'
WHERE  "MissionRunId" = 'MR-STUCK-1' AND "Status" = 'NotStarted';

UPDATE public."Robots" SET "CurrentMissionId" = NULL
WHERE  "CurrentMissionId" = 'MR-STUCK-1';

-- Verify inside the transaction; any failure aborts before COMMIT.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."MissionRuns" WHERE "Id" = 'MR-STUCK-1' AND "Status" = 'Aborted') THEN
        RAISE EXCEPTION 'Verify: MR-STUCK-1 is not Aborted';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Robots" WHERE "CurrentMissionId" = 'MR-STUCK-1') THEN
        RAISE EXCEPTION 'Verify: a robot still points at MR-STUCK-1';
    END IF;
    RAISE NOTICE 'Verify OK: MR-STUCK-1 aborted, robot released.';
END $$;

ROLLBACK;  -- COMMIT;
