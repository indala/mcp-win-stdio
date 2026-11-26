# External & Third-Party Packages Reference (`mcp-win-stdio`)

Agent reference index for every PyPI package, dev/build tool, and external CLI/system dependency used in `mcp-win-stdio`. Each `.md` file provides two-column reference tables (**Function Name / Variable** | **Attributes & Description**).

## 1. Third-Party Runtime PyPI Packages

| Package | Version, Scope & Purpose |
| :--- | :--- |
| [`mcp`](./mcp.md) | `>=1.2.0` *(symbol snapshot: `2.3.0`)* · 215 documented items<br>Core Model Context Protocol (MCP) Python SDK for server creation, `@mcp.tool()` registration, transport security, and protocol types. |
| [`pyyaml`](./pyyaml.md) | `>=6.0.3` · 87 documented items<br>YAML parsing and serialization for Hub configuration (`hub.yaml`) and registry profiles. |
| [`tomli`](./tomli.md) | `>=2.0.1 (`python_version < '3.11'`)` · 3 documented items<br>TOML parser fallback for Python 3.10 (standard library `tomllib` provides the matching API on Python 3.11+). |
| [`pandas`](./pandas.md) | `>=2.0.0` · 106 documented items<br>Tabular DataFrame queries, Excel/CSV I/O, data profiling, cleaning, and SQL-backed transformations. |
| [`openpyxl`](./openpyxl.md) | `>=3.1.0` · 127 documented items<br>Excel `.xlsx` workbook authoring, cell styling, conditional formatting, charts, Excel tables, and coordinate helpers. |
| [`rapidfuzz`](./rapidfuzz.md) | `>=3.0.0` · 17 documented items<br>High-speed fuzzy string matching for Excel key reconciliation and Explorer typo-tolerant file search. |
| [`python-docx`](./python-docx.md) | `>=1.1.0` · 44 documented items<br>Word `.docx` document creation, layout/margins, typography, images, tables, and XML namespace inspection. |
| [`pywin32`](./pywin32.md) | `>=306 (Windows only)` · 216 documented items<br>Windows COM automation (`Excel.Application`, `Word.Application`), apartment initialization (`pythoncom`), and Windows Credential Manager (`win32cred`). |
| [`pathspec`](./pathspec.md) | `>=0.12.0 (`>=0.11.0` in `requirements.txt`)` · 11 documented items<br>`.gitignore` gitwildmatch pattern matching for token-safe directory traversal in Explorer. |
| [`psycopg2-binary`](./psycopg2-binary.md) | `>=2.9.0` · 170 documented items<br>PostgreSQL database adapter, dict cursors (`RealDictCursor`), and batch execution (`execute_batch`). |
| [`pymysql`](./pymysql.md) | `>=1.1.0` · 40 documented items<br>Pure-Python MySQL / MariaDB client driver and `DictCursor` support. |
| [`sqlalchemy`](./sqlalchemy.md) | `>=2.0.0` · 119 documented items<br>SQL engine abstraction (`create_engine`, `text`) for Excel-to-DB streaming, upserting, and dataset reconciliation. |
| [`paramiko`](./paramiko.md) | `>=3.0.0` · 87 documented items<br>Pure-Python SSHv2 connections, `~/.ssh/config` parsing (`SSHConfig`), interactive PTY channels, SFTP, and port forwarding. |
| [`cryptography`](./cryptography.md) | `>=3.3.0` · 148 documented items<br>Self-signed X.509 certificate & RSA private key generation for `mws tunnel` direct HTTPS mode and SSH key handling. |
| [`networkx`](./networkx.md) | `>=3.2.1 (`>=3.0` in `rag` & `requirements.txt`)` · 100 documented items<br>Link-graph trees in RAG and directed multigraph (`MultiDiGraph`) architecture modeling/tracing in Arch. |
| [`numpy`](./numpy.md) | `>=1.24.0` · 117 documented items<br>Numerical arrays and vector computations for RAG hybrid search and Excel-DB streaming. |
| [`playwright`](./playwright.md) | `>=1.40.0` · 110 documented items<br>Headless Chromium automation (`async_playwright`) for crawling JS-rendered documentation in RAG. |
| [`beautifulsoup4`](./beautifulsoup4.md) | `>=4.12.0` · 22 documented items<br>HTML/XML parsing and DOM extraction (`BeautifulSoup`) for RAG documentation ingestion. |
| [`scikit-learn`](./scikit-learn.md) | `Optional (`sklearn`)` · 63 documented items<br>Optional TF-IDF vectorization (`TfidfVectorizer`) and `cosine_similarity` scoring in RAG hybrid search. |
| [`jsonschema`](./jsonschema.md) | `>=4.0.0` (declared in root `pyproject.toml`) · 11 documented items<br>JSON Schema Draft 2020-12 validation (`Draft202012Validator`) for workflow definitions and tool arguments. |
| [`starlette`](./starlette.md) | `>=0.27.0` (declared in root `pyproject.toml`) · 106 documented items<br>ASGI app routing, HTTP middleware (`BaseHTTPMiddleware`), request/response primitives, and background tasks for the HTTP Hub & Tunnel. |
| [`uvicorn`](./uvicorn.md) | `>=0.23.0` (declared in root `pyproject.toml`) · 3 documented items<br>ASGI HTTP/HTTPS server running the Streamable HTTP MCP bridge and tunnel endpoints. |

## 2. Development, Testing & Build Packages

| Package | Version, Scope & Purpose |
| :--- | :--- |
| [`pytest`](./pytest.md) | `>=8.0.0` · 19 documented items<br>Test runner, fixtures, parametrization, exception assertions (`pytest.raises`), and skip markers. |
| [`pytest-asyncio`](./pytest-asyncio.md) | `>=0.23.0` · 4 documented items<br>Asyncio test execution support for `async def` tests (`@pytest.mark.asyncio`, event loop fixtures). |
| [`ruff`](./ruff.md) | `>=0.9.0` · 8 documented items<br>Fast Python linter and formatter (`E`, `F`, `W`, `I` rules configured in root `pyproject.toml`). |
| [`build`](./build.md) | `>=1.2.0` · 8 documented items<br>PEP 517 Python package builder (`python -m build`) producing `.whl` and `.tar.gz` distributions. |
| [`twine`](./twine.md) | `>=5.0.0` · 8 documented items<br>PyPI distribution uploader and validator (`twine upload`, `twine check`). |
| [`hatchling`](./hatchling.md) | `>=1.25.0` · 5 documented items<br>PEP 517 build backend used across the root package and all 10 `packages/mcp-win-stdio-*` wheels. |

## 3. External CLIs, Desktop Apps & Remote Tools

| External Package / Tool | Prerequisite & Purpose |
| :--- | :--- |
| [`git (Git CLI)`](./git.md) | `winget install --id Git.Git -e` · 16 commands/vars<br>Local Git CLI used for repository inspection, diffs, commits, branching, stashing, worktrees, blame, and repo status. |
| [`gh (GitHub CLI)`](./gh.md) | `winget install --id GitHub.cli -e` · 11 commands/vars<br>Official GitHub CLI used for PRs, issues, CI workflow runs, releases, gists, code search, and GitHub API requests. |
| [`cloudflared (Cloudflare Tunnel CLI)`](./cloudflared.md) | `winget install --id Cloudflare.cloudflared` (or `brew install cloudflared`) · 9 commands/vars<br>Default HTTPS tunnel provider for `mws tunnel`, exposing the local Streamable HTTP MCP endpoint over `*.trycloudflare.com`. |
| [`ngrok`](./ngrok.md) | `winget install --id Ngrok.Ngrok` (or `brew install ngrok/ngrok/ngrok`) · 6 commands/vars<br>Alternative HTTPS tunnel provider (`--provider ngrok`) with optional custom `--domain` support. |
| [`Node.js & TypeScript (`node`, `tsc`, `npx`)`](./nodejs-tsc.md) | `winget install --id OpenJS.NodeJS -e` / `npm install -D typescript` · 5 commands/vars<br>Runs background `tsc --watch` compiler diagnostics (resolved via local `node_modules/.bin/tsc`, global `tsc`, or `npx tsc`) and Node-based child MCP servers. |
| [`PostgreSQL CLI (`pg_dump`, `psql`)`](./postgresql-cli.md) | PostgreSQL bin utilities on `PATH` · 5 commands/vars<br>Optional native PostgreSQL dump/restore tools invoked by `dump_database` and `restore_database` (with SQL fallback when absent). |
| [`MySQL CLI (`mysqldump`, `mysql`)`](./mysql-cli.md) | MySQL / MariaDB client utilities on `PATH` · 4 commands/vars<br>Optional native MySQL/MariaDB dump/restore utilities invoked by `dump_database` and `restore_database`. |
| [`Package & System Runners (`uv`, `pip`, `winget`, `brew`, `openssl`, `taskkill`)`](./package-managers.md) | OS / Python toolchain binaries · 8 commands/vars<br>Package installation, self-updates, OS tool installation, and Windows process management. |
| [`Remote SSH Host Tools (`systemctl`, `docker`, `pm2`, `journalctl`, package managers)`](./ssh-remote-tools.md) | Installed on target Linux/Unix/Windows remote SSH hosts · 7 commands/vars<br>Remote system, container, service, log, and package inspection commands executed over Paramiko SSH channels. |
