import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")
cur = conn.cursor(cursor_factory=RealDictCursor)

has_pg_stat = False
try:
    cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
    has_pg_stat = bool(cur.fetchone())
except Exception:
    pass

print("pg_stat_statements extension installed:", has_pg_stat)

# Fallback: pg_stat_activity
cur.execute("""
SELECT pid, usename, application_name, client_addr, state, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND pid != pg_backend_pid()
ORDER BY duration DESC NULLS LAST
LIMIT 10;
""")
rows = cur.fetchall()
print(f"Current active queries: {len(rows)}")
