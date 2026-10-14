-- Stuck missions — Ongoing runs with no StartTime, or Ongoing longer than N hours
-- Usage: onboarded sql stuck_missions <hours> [--exec]
-- Rule (MissionRun.cs): StartTime is set when Status becomes Ongoing; null here means the
-- Ongoing transition was written without it, or the ISAR update was lost.
SELECT mr."Id", mr."Name", mr."Status", mr."RobotId", r."Name" AS robot, r."Status" AS robot_status,
       mr."CreationTime", mr."StartTime",
       CASE WHEN mr."StartTime" IS NULL THEN 'no StartTime'
            ELSE 'ongoing ' || round(extract(epoch FROM now() - mr."StartTime") / 3600, 1) || ' h' END AS reason
FROM   public."MissionRuns" mr
LEFT   JOIN public."Robots" r ON r."Id" = mr."RobotId"
WHERE  mr."Status" = 'Ongoing'
  AND  (mr."StartTime" IS NULL OR mr."StartTime" < now() - make_interval(hours => {{HOURS}}))
ORDER  BY mr."CreationTime";
