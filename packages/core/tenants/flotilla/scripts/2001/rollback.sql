-- Ticket 2001 | ROLLBACK — restores the RS1 state from dryrun.
-- Same convention as fix.sql: change the last line to COMMIT; to apply.
BEGIN;
UPDATE public."MissionRuns"
SET    "Status" = 'Ongoing', "EndTime" = NULL, "StatusReason" = NULL
WHERE  "Id" = 'MR-STUCK-1' AND "StatusReason" LIKE 'Ticket 2001:%';
UPDATE public."MissionTasks" SET "Status" = 'NotStarted'
WHERE  "MissionRunId" = 'MR-STUCK-1' AND "Status" = 'Cancelled';
UPDATE public."Robots" r SET "CurrentMissionId" = 'MR-STUCK-1'
FROM   public."MissionRuns" mr
WHERE  mr."Id" = 'MR-STUCK-1' AND r."Id" = mr."RobotId" AND r."CurrentMissionId" IS NULL;
SELECT mr."Id", mr."Status", mr."EndTime", r."CurrentMissionId"
FROM   public."MissionRuns" mr JOIN public."Robots" r ON r."Id" = mr."RobotId"
WHERE  mr."Id" = 'MR-STUCK-1';
ROLLBACK;  -- COMMIT;
