# `hatchling` (>=1.25.0)

> PEP 517 build backend used across the root package and all 10 `packages/mcp-win-stdio-*` wheels.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Development & Build |
| **Version Constraint** | `>=1.25.0` |
| **Declared / Referenced In** | `pyproject.toml` (`[build-system]`, `dev`), all `packages/*/pyproject.toml`, `requirements-dev.txt` |

## Key Functions, Commands & Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `hatchling.build` | `build-backend` · PEP 517 build backend entrypoint referenced in `[build-system] build-backend = 'hatchling.build'`. |
| `build_wheel(wheel_directory, ...)` | `PEP 517 hook` · Builds a binary `.whl` archive from configured package sources. |
| `build_sdist(sdist_directory, ...)` | `PEP 517 hook` · Builds a source `.tar.gz` distribution archive. |
| `build_editable(wheel_directory, ...)` | `PEP 517 hook` · Builds an editable installation wheel (`pip install -e .`). |
| `[tool.hatch.build.targets.wheel].packages` | `config variable` · List of source package directories included in wheels (e.g. `['src/mcp_win_stdio']`). |
