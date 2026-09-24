# mcp-win-stdio-db

Unified Database Model Context Protocol (MCP) server for **PostgreSQL** and **MySQL** with multi-server in-memory pooling, sibling database auto-derivation, cross-schema resolution, and complete DBA operations.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features

- **Polyglot Database Engine**: Handles PostgreSQL (`psycopg2`) and MySQL (`pymysql`) transparently.
- **In-Memory Connection Pooling**: Fast continuous queries with zero reconnection latency.
- **Sibling Database Auto-Derivation**: On PostgreSQL (`localhost:5432`), auto-discovers sibling databases (`showreel`, `dsr`, `location_booking`, `sap`, etc.) on the fly.
- **DBA & Management Tools**: `create_database`, `drop_database` (with safety guard), `clone_database` (instant template clone), `terminate_connections`, `list_active_queries`, `dump_database`, and `restore_database`.
- **Self-Contained `SERVERS` JSON**: Configure in one environment variable without external files.

---

## 📦 Quick Start

### 1. Installation
```powershell
pip install mcp-win-stdio-db
# or for full suite:
pip install mcp-win-stdio[db]
```

### 2. Check Health
```powershell
mws-db doctor
```

### 3. Claude Desktop / Gemini Configuration
```json
"database": {
  "command": "python",
  "args": ["-m", "mcp_win_stdio.db.server"],
  "env": {
    "SERVERS": "{\"showreel\":\"postgresql://postgres:mohan@localhost:5432/showreel\",\"dsr\":\"postgresql://postgres:mohan@localhost:5432/dsr\",\"ijitest\":\"mysql://u116573049_ijitest:Ijitest123@srv604.hstgr.io:3306/u116573049_ijitest_db\"}"
  }
}
```
