# `pytest-asyncio` (>=0.23.0)

> Asyncio test execution support for `async def` tests (`@pytest.mark.asyncio`, event loop fixtures).

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Development & Build |
| **Version Constraint** | `>=0.23.0` |
| **Declared / Referenced In** | `requirements-dev.txt` |

## Key Functions, Commands & Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `@pytest.mark.asyncio` | `decorator` · Marks an `async def` test function or fixture to run on an asyncio event loop. |
| `asyncio_mode` | `ini option` (`'auto'` \\| `'strict'`) · Controls whether async tests/fixtures are automatically treated as asyncio tests in `pyproject.toml` / `pytest.ini`. |
| `asyncio_default_fixture_loop_scope` | `ini option` (`'function'` \\| `'class'` \\| `'module'` \\| `'package'` \\| `'session'`) · Default event loop scope for async fixtures. |
| `event_loop_policy` | `fixture` · Overrideable pytest fixture providing the asyncio event loop policy for test sessions. |
