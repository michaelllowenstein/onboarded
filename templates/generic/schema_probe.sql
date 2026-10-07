-- Schema probe — column listing for any table (Postgres)
-- Usage: onboarded sql schema_probe <schema> <table> [--exec]
SELECT ordinal_position AS column_id,
       column_name,
       data_type,
       character_maximum_length AS max_length,
       is_nullable
FROM   information_schema.columns
WHERE  table_schema = '{{SCHEMA}}'
  AND  table_name   = '{{TABLE}}'
ORDER  BY ordinal_position;
