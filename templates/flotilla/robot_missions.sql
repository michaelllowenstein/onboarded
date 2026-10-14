-- Robot missions — a robot's status, current mission and its 20 most recent runs
-- Usage: onboarded sql robot_missions <RobotName> [--exec]
SELECT r."Id", r."Name", r."Status", r."IsarId", r."CurrentMissionId", r."Deprecated",
       i."InstallationCode"
FROM   public."Robots" r
LEFT   JOIN public."Installations" i ON i."Id" = r."CurrentInstallationId"
WHERE  r."Name" = '{{ROBOT_NAME}}';

SELECT mr."Id", mr."Name", mr."Status", mr."CreationTime", mr."StartTime", mr."EndTime", mr."StatusReason"
FROM   public."MissionRuns" mr
JOIN   public."Robots" r ON r."Id" = mr."RobotId"
WHERE  r."Name" = '{{ROBOT_NAME}}'
ORDER  BY mr."CreationTime" DESC
LIMIT  20;
