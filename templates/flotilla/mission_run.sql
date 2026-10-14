-- Mission run — one run with its robot and tasks (Postgres, Flotilla EF schema)
-- Usage: onboarded sql mission_run <MissionRunId> [--exec]
SELECT mr."Id", mr."Name", mr."Status", mr."StatusReason",
       mr."CreationTime", mr."StartTime", mr."EndTime",
       r."Name" AS robot, r."Status" AS robot_status, r."CurrentMissionId"
FROM   public."MissionRuns" mr
LEFT   JOIN public."Robots" r ON r."Id" = mr."RobotId"
WHERE  mr."Id" = '{{RUN_ID}}';

SELECT t."TaskOrder", t."Status", t."TagId", t."SensorType", t."StartTime", t."EndTime", t."ErrorDescription"
FROM   public."MissionTasks" t
WHERE  t."MissionRunId" = '{{RUN_ID}}'
ORDER  BY t."TaskOrder";
