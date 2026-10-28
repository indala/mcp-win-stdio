# Contributing to mcp-win-stdio

Thank you for your interest in contributing to **`mcp-win-stdio`**! We welcome contributions to make this Windows-optimized Model Context Protocol suite and dynamic gateway (`mws`) faster, more reliable, and more powerful for developers and AI IDEs.

---

## 🏗️ Project Architecture Overview

`mcp-win-stdio` is organized as a modular workspace containing:

- **Root Gateway (`src/mcp_win_stdio/`)**: Central on-demand gateway `mws`, dynamic tool catalog, hub orchestrator, streamable HTTP bridge, and process supervisor.
- **Modular Subpackages (`packages/`)**:
  - `mcp-win-stdio-excel`: High-performance Excel automation & formula engine.
  - `mcp-win-stdio-word`: Word typography, document generation, and PDF conversion.
  - `mcp-win-stdio-explorer`: Native Windows directory & code search engine.
  - `mcp-win-stdio-tsc`: Zero-latency background TypeScript compiler diagnostics.
  - `mcp-win-stdio-db`: Polyglot PostgreSQL & MySQL engine.
  - `mcp-win-stdio-git`: Git repository & GitHub CLI orchestration.
  - `mcp-win-stdio-ssh`: Multi-host SSH connection pool & SFTP.
  - `mcp-win-stdio-rag`: High-speed documentation crawling & semantic search.
  - `mcp-win-stdio-excel-db`: High-throughput DB-to-Excel streaming & reconciliation.
  - `mcp-win-stdio-arch`: Architecture diffing and code diagram generation.

---

## 🛠️ Development Setup

### Prerequisites
- Windows 10/11 or Windows Server (x64)
- Python `>=3.10`
- Git for Windows (`winget install --id Git.Git -e`)
- GitHub CLI (`winget install --id GitHub.cli -e`, optional for GitHub tools)

### Installation
1. Fork the repository on GitHub and clone your fork:
   ```powershell
   git clone https://github.com/<your-username>/mcp-win-stdio.git
   cd mcp-win-stdio
   ```

2. Install core development dependencies:
   ```powershell
   python -m pip install --upgrade pip
   pip install -e .
   pip install pytest ruff build twine hatchling
   ```

3. Install subpackages in editable mode:
   ```powershell
   pip install -e packages/mcp-win-stdio-excel -e packages/mcp-win-stdio-word -e packages/mcp-win-stdio-explorer -e packages/mcp-win-stdio-tsc -e packages/mcp-win-stdio-db -e packages/mcp-win-stdio-git -e packages/mcp-win-stdio-ssh -e packages/mcp-win-stdio-rag -e packages/mcp-win-stdio-excel-db -e packages/mcp-win-stdio-arch
   ```

---

## 🧪 Testing & Code Quality

Before submitting a pull request, verify that all linting checks and automated unit tests pass:

1. **Linting & Code Formatting:**
   ```powershell
   python -m ruff check .
   ```

2. **Run Full Test Suite:**
   ```powershell
   python -m pytest tests/
   ```

3. **Verify Builds:**
   ```powershell
   python scripts/build_all.py
   twine check dist/*
   ```

---

## 📋 Guidelines for Contributions

### 1. Windows Safety & Process Isolation
- Never use `os.kill(pid, 0)` on Windows; use Win32 `OpenProcess` with `SYNCHRONIZE` or `WaitForSingleObject`.
- Pass `stdin=subprocess.DEVNULL` to `subprocess.run` / `subprocess.Popen` when spawning external CLI processes (`git`, `gh`, `pwsh`) to avoid handle duplication errors in headless or non-console environments.
- Protect against Windows path quoting problems by avoiding `shell=True` where possible.

### 2. Zero Context Bloat
- Tools registered in `mws` should produce compact, structured JSON payloads.
- Truncate long terminal or diff outputs safely (e.g. capped lines/characters) to avoid flooding LLM context windows.

### 3. Preserving User Configuration
- Never mutate or overwrite existing user configurations located in `~/.mcp-win-stdio/` without explicit caller confirmation.
- Unit tests must be hermetic and mock or isolate config file access using pytest `tmp_path` fixtures.

---

## 🚀 Submitting a Pull Request

1. Create a feature branch: `git checkout -b feat/my-new-feature`
2. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat(...)`: New features
   - `fix(...)`: Bug fixes
   - `test(...)`: Adding or updating tests
   - `docs(...)`: Documentation updates
3. Push to your fork: `git push origin feat/my-new-feature`
4. Open a Pull Request against the `main` branch of `indala/mcp-win-stdio`.
5. Ensure the CI workflow passes on GitHub Actions.
