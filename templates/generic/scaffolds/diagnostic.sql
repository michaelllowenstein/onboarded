-- Ticket {{TICKET_ID}} | Diagnostic (read only)
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}}

-- Q0: schema probe
SELECT ordinal_position, column_name, data_type, is_nullable
FROM   information_schema.columns
WHERE  table_schema = split_part('{{TARGET_TABLE}}', '.', 1)
  AND  table_name   = split_part('{{TARGET_TABLE}}', '.', 2)
ORDER  BY ordinal_position;

-- Q1: data state — fill in with ticket-specific identifiers
-- SELECT ... FROM {{TARGET_TABLE}} WHERE ...;
