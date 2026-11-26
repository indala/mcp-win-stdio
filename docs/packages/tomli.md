# `tomli` (>=2.0.1 (`python_version < '3.11'`))

> TOML parser fallback for Python 3.10 (standard library `tomllib` provides the matching API on Python 3.11+).

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=2.0.1 (`python_version < '3.11'`)` |
| **Declared / Referenced In** | `pyproject.toml` |

## Public Functions, Classes & Variables

### `tomllib`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class TOMLDecodeError`** | `class` · Init: `(msg: 'str' = <class 'tomllib._parser.DEPRECATED_DEFAULT'>, doc: 'str' = <class 'tomllib._parser.DEPRECATED_DEFAULT'>, pos: 'Pos' = <class 'tomllib._parser.DEPRECATED_DEFAULT'>, *args: 'Any')` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>An error raised if a document is not valid TOML. |
| `load()` | `function` · Signature: `(fp: 'IO[bytes]', /, *, parse_float: 'ParseFloat' = <class 'float'>) -> 'dict[str, Any]'`<br>Parse TOML from a binary file object. |
| `loads()` | `function` · Signature: `(s: 'str', /, *, parse_float: 'ParseFloat' = <class 'float'>) -> 'dict[str, Any]'`<br>Parse TOML from a string. |
