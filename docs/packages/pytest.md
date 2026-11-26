# `pytest` (>=8.0.0)

> Test runner, fixtures, parametrization, exception assertions (`pytest.raises`), and skip markers.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Development & Build |
| **Version Constraint** | `>=8.0.0` |
| **Declared / Referenced In** | `pyproject.toml` (`[project.optional-dependencies].dev`), `requirements-dev.txt`, `tests/` |

## Public Functions, Classes & Variables

### `pytest`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class ExitCode`** | `class` · Init: `(*values)` · Attrs: `INTERNAL_ERROR`, `INTERRUPTED`, `MAX_WARNINGS_ERROR`, `NO_TESTS_COLLECTED`, `OK`, `TESTS_FAILED`, `USAGE_ERROR`, `as_integer_ratio`, `bit_count`, `bit_length` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Encodes the valid exit codes by pytest. |
| `HIDDEN_PARAM` | `variable` · Type: `_HiddenParam` · Value: `<_HiddenParam.token: 0>` |
| **`class PytestAssertRewriteWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted by the pytest assert rewrite module. |
| **`class PytestCacheWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted by the cache plugin in various situations. |
| **`class PytestCollectionWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted when pytest is not able to collect a file or symbol in a module. |
| **`class PytestConfigWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted for configuration issues. |
| **`class PytestDeprecationWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning class for features that will be removed in a future version. |
| **`class PytestExperimentalApiWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `simple`, `with_traceback` · Methods: `add_note(self, note, /)`, `simple(apiname: 'str') -> 'PytestExperimentalApiWarning'`, `with_traceback(self, tb, /)`<br>Warning category used to denote experiments in pytest. |
| **`class PytestFDWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>When the lsof plugin finds leaked fds. |
| **`class PytestRemovedIn10Warning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning class for features that will be removed in pytest 10. |
| **`class PytestReturnNotNoneWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted when a test function returns a value other than ``None``. |
| **`class PytestUnhandledThreadExceptionWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>An unhandled exception occurred in a :class:`~threading.Thread`. |
| **`class PytestUnknownMarkWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning emitted on use of unknown markers. |
| **`class PytestUnraisableExceptionWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>An unraisable exception was reported. |
| **`class PytestWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Base class for all warnings emitted by pytest. |
| **`class UsageError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error in pytest usage or invocation. |
| `__version__` | `variable` · Type: `str` · Value: `'9.1.1'` |
| `mark` | `variable` · Type: `MarkGenerator` · Value: `<_pytest.mark.structures.MarkGenerator object at 0x000001...` |
| `version_tuple` | `variable` · Type: `tuple` · Value: `(9, 1, 1)` |
