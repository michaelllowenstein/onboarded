-- ADO #{{TICKET_ID}} | Diagnostic
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}}
-- Run on: msi-prod-readonly (READ ONLY)

-- Q0: Schema probe
SELECT c.column_id, c.name AS ColumnName, t.name AS TypeName, c.is_nullable
FROM   sys.columns c
JOIN   sys.types   t ON t.user_type_id = c.user_type_id
WHERE  c.object_id = OBJECT_ID(N'{{TARGET_TABLE}}')
ORDER  BY c.column_id;
GO

-- Q1: Data state (fill WHERE clause with ticket-specific identifiers)
-- TODO: cluster-specific diagnostic query