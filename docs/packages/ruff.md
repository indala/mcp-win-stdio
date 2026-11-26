# `ruff` (>=0.9.0)

> Fast Python linter and formatter (`E`, `F`, `W`, `I` rules configured in root `pyproject.toml`).

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Development & Build |
| **Version Constraint** | `>=0.9.0` |
| **Declared / Referenced In** | `pyproject.toml` (`dev`, `[tool.ruff]`), `requirements-dev.txt` |

## Key Functions, Commands & Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `ruff check [PATHS]` | `CLI command` · Run linter checks (`--fix`, `--select`, `--ignore`, `--output-format`, `--watch`). Configured in `[tool.ruff.lint]`. |
| `ruff format [PATHS]` | `CLI command` · Format Python source files (`--check`, `--diff`, `--line-length`). Configured with `line-length = 120`, `target-version = 'py310'`. |
| `ruff rule <RULE>` | `CLI command` · Explain a lint rule (e.g. `E501`, `F401`, `I001`). |
| `ruff clean` | `CLI command` · Clear `.ruff_cache` in current directory and subdirectories. |
| `ruff server` | `CLI command` · Run the Ruff LSP language server for editor integration. |
| `ruff analyze` | `CLI command` · Run static analysis over Python source code. |
| `[tool.ruff]` (`line-length`, `target-version`, `exclude`) | `config variables` · Set in `pyproject.toml` (`line-length = 120`, `target-version = 'py310'`). |
| `[tool.ruff.lint]` (`select`, `ignore`) | `config variables` · Set in `pyproject.toml` (`select = ['E', 'F', 'W', 'I']`, `ignore = ['E501', 'E402', 'E722', 'F841', 'W293', 'W291', 'E741', 'F401']`). |
