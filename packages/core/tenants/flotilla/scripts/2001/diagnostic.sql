-- Ticket 2001 | Diagnostic (read only — safe as ob_reader)
-- Symptom: robot Taurob-1 shows Busy, its queue (MR-QUEUE-1) never starts.
-- Hypothesis: run MR-STUCK-1 is Ongoing with no StartTime (ISAR never confirmed the start,
-- or the update was lost), and the robot's CurrentMissionId still points at it, so
-- MissionSchedulingService.StartNextMissionRunIfSystemIsAvailable never sees the robot free.

-- Q0: schema probe
SELECT column_name, data_type, is_nullable
FROM   information_schema.columns
WHERE  table_schema = 'public' AND table_name = 'MissionRuns'
ORDER  BY ordinal_position;

-- Q1: every Ongoing run with no StartTime, and what its robot thinks
SELECT mr."Id", mr."Name", mr."Status", mr."CreationTime", mr."StartTime",
       r."Name" AS robot, r."Status" AS robot_status, r."CurrentMissionId",
       (r."CurrentMissionId" = mr."Id") AS robot_points_here
FROM   public."MissionRuns" mr
JOIN   public."Robots" r ON r."Id" = mr."RobotId"
WHERE  mr."Status" = 'Ongoing' AND mr."StartTime" IS NULL
ORDER  BY mr."CreationTime";

-- Q2: runs queued behind it on the same robot
SELECT mr."Id", mr."Name", mr."Status", mr."CreationTime"
FROM   public."MissionRuns" mr
WHERE  mr."RobotId" = (SELECT "RobotId" FROM public."MissionRuns" WHERE "Id" = 'MR-STUCK-1')
  AND  mr."Status" IN ('Queued', 'Pending')
ORDER  BY mr."CreationTime";

-- Q3: its tasks
SELECT "Id", "TaskOrder", "Status", "TagId" FROM public."MissionTasks"
WHERE  "MissionRunId" = 'MR-STUCK-1' ORDER BY "TaskOrder";
