import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/showreel_dev")
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("""
SELECT 
    l.locktype, l.mode, l.granted,
    a.pid, a.usename, a.application_name, a.client_addr,
    now() - a.query_start AS duration,
    a.state,
    a.query
FROM pg_locks l
JOIN pg_stat_activity a ON l.pid = a.pid
WHERE a.pid != pg_backend_pid()
LIMIT 10;
""")
locks = cur.fetchall()
print(f"Active non-self locks: {len(locks)}")
for lk in locks:
    print(f"  PID {lk['pid']} ({lk['usename']}) - {lk['locktype']} / {lk['mode']} - state: {lk['state']}")
