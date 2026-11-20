-- Read-only; use a trusted BYPASSRLS operator connection, never the API role.
BEGIN READ ONLY;
SET LOCAL row_security = off;
SELECT left(tenant_id::text, 8) AS tenant, project_id, code, count(*) AS duplicates
FROM le_knode GROUP BY tenant_id, project_id, code HAVING count(*) > 1;
ROLLBACK;
