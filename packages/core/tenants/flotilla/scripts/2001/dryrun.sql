-- Ticket 2001 | DRY RUN — always rolls back (last line is ROLLBACK, never COMMIT).
-- RS1 is the pre-fix state: rollback.sql restores exactly this.
BEGIN;

CREATE TEMP TABLE t_run   ON COMMIT DROP AS SELECT * FROM public."MissionRuns"  WHERE "Id" = 'MR-STUCK-1';
CREATE TEMP TABLE t_tasks ON COMMIT DROP AS SELECT * FROM public."MissionTasks" WHERE "MissionRunId" = 'MR-STUCK-1';
CREATE TEMP TABLE t_robot ON COMMIT DROP AS
    SELECT r.* FROM public."Robots" r JOIN t_run ON r."Id" = t_run."RobotId";
CREATE TEMP TABLE t_others ON COMMIT DROP AS
    SELECT "Id", "Status", "EndTime" FROM public."MissionRuns" WHERE "Id" <> 'MR-STUCK-1';

-- RS1: before
SELECT t_run."Id", t_run."Status", t_run."StartTime", t_run."EndTime", t_run."StatusReason",
       t_robot."Name" AS robot, t_robot."CurrentMissionId"
FROM   t_run CROSS JOIN t_robot;

-- simulated fix
UPDATE public."MissionRuns"
SET    "Status" = 'Aborted', "EndTime" = now(),
       "StatusReason" = 'Ticket 2001: Ongoing with no StartTime; aborted by DBA'
WHERE  "Id" = 'MR-STUCK-1' AND "Status" = 'Ongoing' AND "StartTime" IS NULL;
UPDATE public."MissionTasks" SET "Status" = 'Cancelled'
WHERE  "MissionRunId" = 'MR-STUCK-1' AND "Status" = 'NotStarted';
UPDATE public."Robots" SET "CurrentMissionId" = NULL
WHERE  "Id" = (SELECT "RobotId" FROM t_run) AND "CurrentMissionId" = 'MR-STUCK-1';

-- RS2: after
SELECT mr."Id", mr."Status", mr."EndTime", mr."StatusReason", r."CurrentMissionId"
FROM   public."MissionRuns" mr JOIN public."Robots" r ON r."Id" = mr."RobotId"
WHERE  mr."Id" = 'MR-STUCK-1';

-- RS3: gates — every row must be PASS before fix.sql runs
WITH s AS (
    SELECT (SELECT count(*) FROM t_run WHERE "Status" = 'Ongoing' AND "StartTime" IS NULL)        AS was_stuck,
           (SELECT count(*) FROM public."MissionRuns" WHERE "Id" = 'MR-STUCK-1' AND "Status" = 'Aborted'
                                                         AND "EndTime" IS NOT NULL)                AS aborted,
           (SELECT count(*) FROM public."MissionTasks" WHERE "MissionRunId" = 'MR-STUCK-1'
                                                          AND "Status" = 'NotStarted')             AS open_tasks,
           (SELECT count(*) FROM public."Robots" WHERE "CurrentMissionId" = 'MR-STUCK-1')           AS robot_refs,
           NOT EXISTS (SELECT "Id", "Status", "EndTime" FROM public."MissionRuns" WHERE "Id" <> 'MR-STUCK-1'
                       EXCEPT SELECT * FROM t_others)                                             AS others_untouched
)
SELECT gate, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result
FROM s, LATERAL (VALUES
    ('1 run was Ongoing with no StartTime', was_stuck = 1),
    ('2 run is Aborted with EndTime',       aborted = 1),
    ('3 no NotStarted tasks remain',        open_tasks = 0),
    ('4 no robot points at the run',        robot_refs = 0),
    ('5 no other run changed',              others_untouched)
) g(gate, ok);

ROLLBACK;
