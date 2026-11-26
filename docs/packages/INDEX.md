# `mcp-win-stdio` Packages Index (Agent Reference)

Master index of all **37** third-party PyPI packages, development/build tools, and external CLIs/system dependencies used across `mcp-win-stdio`. Click any package name to open its symbol-level reference (`Function Name / Variable` | `Attributes & Description`).

> Also see [`docs/packages/README.md`](./README.md) for category counts and [`docs/README.md`](../README.md) for architecture & guide docs.

---

## 1. Master Index (All Packages & External Tools)

| Package | Category | Version / Prerequisite | Used By (`mcp-win-stdio`) | Key Symbols / Commands |
| :--- | :--- | :--- | :--- | :--- |
| [`mcp`](./mcp.md) | Runtime (PyPI) | `>=1.2.0` *(snapshot: `2.3.0`)* | All 11 packages | `MCPServer`, `FastMCP`, `Context`, `TransportSecuritySettings`, `CallToolResult`, `Tool` |
| [`pyyaml`](./pyyaml.md) | Runtime (PyPI) | `>=6.0.3` | `mcp-win-stdio` (core) | `safe_load()`, `safe_dump()`, `YAMLError` |
| [`tomli`](./tomli.md) | Runtime (PyPI) | `>=2.0.1` (`py<3.11`) | `mcp-win-stdio` (core) | `load()`, `loads()`, `TOMLDecodeError` (`tomllib` on 3.11+) |
| [`pandas`](./pandas.md) | Runtime (PyPI) | `>=2.0.0` | `excel`, `excel-db` | `DataFrame`, `Series`, `read_excel()`, `read_csv()`, `merge()`, `concat()` |
| [`openpyxl`](./openpyxl.md) | Runtime (PyPI) | `>=3.1.0` | `excel`, `excel-db` | `Workbook`, `load_workbook()`, `styles`, `chart`, `formatting.rule`, `Table` |
| [`rapidfuzz`](./rapidfuzz.md) | Runtime (PyPI) | `>=3.0.0` | `excel`, `explorer` | `fuzz.ratio()`, `fuzz.WRatio()`, `process.extract()` |
| [`python-docx`](./python-docx.md) | Runtime (PyPI) | `>=1.1.0` | `word` | `Document()`, `Inches`, `Pt`, `RGBColor`, `WD_ORIENT`, `WD_ALIGN_PARAGRAPH`, `nsmap` |
| [`pywin32`](./pywin32.md) | Runtime (PyPI) | `>=306` (Windows) | `core`, `excel`, `word` | `win32com.client.DispatchEx()`, `pythoncom.CoInitialize()`, `win32cred` |
| [`pathspec`](./pathspec.md) | Runtime (PyPI) | `>=0.12.0` (`>=0.11.0`) | `explorer` | `PathSpec.from_lines()`, `GitIgnoreSpec` |
| [`psycopg2-binary`](./psycopg2-binary.md) | Runtime (PyPI) | `>=2.9.0` | `core`, `db` | `connect()`, `RealDictCursor`, `execute_batch()`, `extensions` |
| [`pymysql`](./pymysql.md) | Runtime (PyPI) | `>=1.1.0` | `core`, `db` | `connect()`, `DictCursor`, `Connection`, `Cursor` |
| [`sqlalchemy`](./sqlalchemy.md) | Runtime (PyPI) | `>=2.0.0` | `excel-db` | `create_engine()`, `text()`, `Engine`, `Connection` |
| [`paramiko`](./paramiko.md) | Runtime (PyPI) | `>=3.0.0` | `core`, `ssh` | `SSHClient`, `AutoAddPolicy`, `SSHConfig`, `SFTPClient`, `Channel` |
| [`cryptography`](./cryptography.md) | Runtime (PyPI) | `>=3.3.0` | `core`, `ssh` | `x509.CertificateBuilder`, `rsa.generate_private_key()`, `hashes`, `serialization`, `NameOID` |
| [`networkx`](./networkx.md) | Runtime (PyPI) | `>=3.2.1` (`>=3.0`) | `arch`, `rag` | `MultiDiGraph`, `DiGraph`, `shortest_path()` |
| [`numpy`](./numpy.md) | Runtime (PyPI) | `>=1.24.0` | `excel-db`, `rag` | `ndarray`, `array()`, `dot()`, `linalg` |
| [`playwright`](./playwright.md) | Runtime (PyPI) | `>=1.40.0` | `core`, `rag` | `async_playwright()`, `Browser`, `BrowserContext`, `Page`, `Locator` |
| [`beautifulsoup4`](./beautifulsoup4.md) | Runtime (PyPI) | `>=4.12.0` | `rag` (manifest) | `BeautifulSoup`, `Tag`, `NavigableString` |
| [`scikit-learn`](./scikit-learn.md) | Optional (PyPI) | Optional (`sklearn`) | `rag` | `TfidfVectorizer`, `cosine_similarity()` |
| [`jsonschema`](./jsonschema.md) | Runtime (PyPI) | `>=4.0.0` (root `pyproject.toml`) | `core` (`workflows.py`) | `Draft202012Validator`, `validate()`, `ValidationError` |
| [`starlette`](./starlette.md) | Runtime (PyPI) | `>=0.27.0` (root `pyproject.toml`) | `core` (`hub`, `tunnel`) | `Starlette`, `Request`, `JSONResponse`, `HTMLResponse`, `RedirectResponse`, `BaseHTTPMiddleware`, `Route`, `BackgroundTask` |
| [`uvicorn`](./uvicorn.md) | Runtime (PyPI) | `>=0.23.0` (root `pyproject.toml`) | `core` (`cli.py`, `tunnel`) | `uvicorn.run()`, `Config`, `Server` |
| [`pytest`](./pytest.md) | Dev / Test (PyPI) | `>=8.0.0` | `tests/` | `pytest.fixture`, `pytest.raises()`, `pytest.mark`, `pytest.skip()` |
| [`pytest-asyncio`](./pytest-asyncio.md) | Dev / Test (PyPI) | `>=0.23.0` | `requirements-dev.txt` | `@pytest.mark.asyncio`, `asyncio_mode` |
| [`ruff`](./ruff.md) | Dev / Lint (PyPI) | `>=0.9.0` | `pyproject.toml` | `ruff check`, `ruff format`, `[tool.ruff.lint]` |
| [`build`](./build.md) | Dev / Build (PyPI) | `>=1.2.0` | `pyproject.toml`, `requirements-dev.txt` | `python -m build`, `ProjectBuilder` |
| [`twine`](./twine.md) | Dev / Build (PyPI) | `>=5.0.0` | `pyproject.toml`, `requirements-dev.txt` | `twine upload`, `twine check` |
| [`hatchling`](./hatchling.md) | Build Backend | `>=1.25.0` | All `pyproject.toml` files | `hatchling.build`, `build_wheel()`, `build_sdist()` |
| [`git`](./git.md) | External CLI | `winget install Git.Git` | `git`, `explorer`, `core` | `git status`, `diff`, `log`, `commit`, `branch`, `worktree`, `GIT_TERMINAL_PROMPT` |
| [`gh`](./gh.md) | External CLI | `winget install GitHub.cli` | `git`, `core` | `gh pr`, `gh issue`, `gh run`, `gh api`, `gh auth`, `GH_PROMPT_DISABLED` |
| [`cloudflared`](./cloudflared.md) | External CLI | `winget install Cloudflare.cloudflared` | `core` (`tunnel.py`, `cli.py`) | `cloudflared tunnel --url`, `--version`, `api.trycloudflare.com` |
| [`ngrok`](./ngrok.md) | External CLI | `winget install Ngrok.Ngrok` | `core` (`tunnel.py`, `cli.py`) | `ngrok http`, `--domain`, `ngrok config add-authtoken` |
| [`Node.js & tsc`](./nodejs-tsc.md) | External CLI | `winget install OpenJS.NodeJS` | `tsc`, `core` (`process_pool.py`) | `node`, `tsc --watch --noEmit`, `npx tsc` |
| [`PostgreSQL CLI`](./postgresql-cli.md) | External CLI | PostgreSQL on `PATH` | `db`, `core` (`cli.py`) | `pg_dump`, `psql`, `PGPASSWORD` |
| [`MySQL CLI`](./mysql-cli.md) | External CLI | MySQL/MariaDB on `PATH` | `db`, `core` (`cli.py`) | `mysqldump`, `mysql` |
| [`Package & System Runners`](./package-managers.md) | External CLI | OS / toolchain | `core` (`installer.py`, `external_updater.py`) | `uv`, `uvx`, `pip`, `winget`, `brew`, `taskkill`, `cmd.exe` |
| [`Remote SSH Tools`](./ssh-remote-tools.md) | Remote Host CLIs | Target SSH hosts | `ssh` | `systemctl`, `docker`, `pm2`, `journalctl`, `dpkg-query`/`rpm`/`apk`/`apt`/`npm`/`pip` |

---

## 2. Reverse Lookup: By `mcp-win-stdio` Workspace Package

| Workspace Package | External & Third-Party Dependencies Used |
| :--- | :--- |
| **`mcp-win-stdio`** *(core CLI, Hub, Tunnel)* | [`mcp`](./mcp.md), [`pyyaml`](./pyyaml.md), [`tomli`](./tomli.md), [`jsonschema`](./jsonschema.md), [`starlette`](./starlette.md), [`uvicorn`](./uvicorn.md), [`cryptography`](./cryptography.md), [`pywin32`](./pywin32.md), [`psycopg2-binary`](./psycopg2-binary.md), [`pymysql`](./pymysql.md), [`paramiko`](./paramiko.md), [`playwright`](./playwright.md), [`cloudflared`](./cloudflared.md), [`ngrok`](./ngrok.md), [`git`](./git.md), [`gh`](./gh.md), [`Package & System Runners`](./package-managers.md) |
| **`mcp-win-stdio-arch`** | [`mcp`](./mcp.md), [`networkx`](./networkx.md) |
| **`mcp-win-stdio-db`** | [`mcp`](./mcp.md), [`psycopg2-binary`](./psycopg2-binary.md), [`pymysql`](./pymysql.md), [`PostgreSQL CLI`](./postgresql-cli.md), [`MySQL CLI`](./mysql-cli.md) |
| **`mcp-win-stdio-excel`** | [`mcp`](./mcp.md), [`pandas`](./pandas.md), [`openpyxl`](./openpyxl.md), [`rapidfuzz`](./rapidfuzz.md), [`pywin32`](./pywin32.md) |
| **`mcp-win-stdio-excel-db`** | [`mcp`](./mcp.md), [`pandas`](./pandas.md), [`openpyxl`](./openpyxl.md), [`sqlalchemy`](./sqlalchemy.md), [`numpy`](./numpy.md) |
| **`mcp-win-stdio-explorer`** | [`mcp`](./mcp.md), [`pathspec`](./pathspec.md), [`rapidfuzz`](./rapidfuzz.md), [`git`](./git.md) |
| **`mcp-win-stdio-git`** | [`mcp`](./mcp.md), [`git`](./git.md), [`gh`](./gh.md) |
| **`mcp-win-stdio-rag`** | [`mcp`](./mcp.md), [`networkx`](./networkx.md), [`numpy`](./numpy.md), [`playwright`](./playwright.md), [`beautifulsoup4`](./beautifulsoup4.md), [`scikit-learn`](./scikit-learn.md) |
| **`mcp-win-stdio-ssh`** | [`mcp`](./mcp.md), [`paramiko`](./paramiko.md), [`cryptography`](./cryptography.md), [`Remote SSH Tools`](./ssh-remote-tools.md) |
| **`mcp-win-stdio-tsc`** | [`mcp`](./mcp.md), [`Node.js & tsc`](./nodejs-tsc.md) |
| **`mcp-win-stdio-word`** | [`mcp`](./mcp.md), [`python-docx`](./python-docx.md), [`pywin32`](./pywin32.md) |
| **Root Dev / Test / Build (`tests/`, `pyproject.toml`)** | [`pytest`](./pytest.md), [`pytest-asyncio`](./pytest-asyncio.md), [`ruff`](./ruff.md), [`build`](./build.md), [`twine`](./twine.md), [`hatchling`](./hatchling.md) |
