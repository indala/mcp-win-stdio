# `build` (>=1.2.0)

> PEP 517 Python package builder (`python -m build`) producing `.whl` and `.tar.gz` distributions.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Development & Build |
| **Version Constraint** | `>=1.2.0` |
| **Declared / Referenced In** | `pyproject.toml` (`dev`), `requirements-dev.txt` |

## Public Functions, Classes & Variables

### `build`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class BuildBackendException`** | `class` · Init: `(exception: 'Exception', description: 'str \| None' = None) -> 'None'` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when a backend operation fails. |
| **`class BuildException`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised by ``build`` when a build cannot proceed. |
| **`class BuildSystemTableValidationError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when the ``[build-system]`` table in pyproject.toml is invalid. |
| **`class FailedProcessError`** | `class` · Init: `(exception: 'subprocess.CalledProcessError', description: 'str') -> 'None'` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when a setup or preparation operation fails. |
| **`class ProjectBuilder`** | `class` · Init: `(source_dir: 'StrPath', python_executable: 'str' = 'C:\\Users\\admin\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe', runner: 'SubprocessRunner' = <function default_subprocess_runner at 0x000001A4AEE4F110>) -> 'None'` · Attrs: `build`, `build_system_requires`, `check_dependencies`, `from_isolated_env`, `get_requires_for_build`, `metadata_path`, `prepare`, `python_executable`, `source_dir` · Methods: `build(self, distribution: 'Distribution', output_directory: 'StrPath', config_settings: 'ConfigSettings \| None' = None, metadata_directory: 'str \| None' = None) -> 'str'`, `check_dependencies(self, distribution: 'Distribution', config_settings: 'ConfigSettings \| None' = None) -> 'set[tuple[str, ...]]'`, `from_isolated_env(env: 'env.IsolatedEnv', source_dir: 'StrPath', runner: 'SubprocessRunner' = <function default_subprocess_runner at 0x000001A4AEE4F110>) -> 'Self'`, `get_requires_for_build(self, distribution: 'Distribution', config_settings: 'ConfigSettings \| None' = None) -> 'set[str]'`, `metadata_path(self, output_directory: 'StrPath') -> 'str'`, `prepare(self, distribution: 'Distribution', output_directory: 'StrPath', config_settings: 'ConfigSettings \| None' = None) -> 'str \| None'`<br>The PEP 517 consumer API. |
| **`class TypoWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning raised when a possible typo is found. |
| `__version__` | `variable` · Type: `str` · Value: `'1.6.1'` |
| `check_dependency()` | `function` · Signature: `(req_string: 'str', ancestral_req_strings: 'tuple[str, ...]' = (), parent_extras: 'AbstractSet[str]' = frozenset()) -> 'Iterator[tuple[str, ...]]'`<br>Verify that a dependency and all of its dependencies are met. |
