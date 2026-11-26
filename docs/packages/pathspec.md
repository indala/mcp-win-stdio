# `pathspec` (>=0.12.0 (`>=0.11.0` in `requirements.txt`))

> `.gitignore` gitwildmatch pattern matching for token-safe directory traversal in Explorer.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=0.12.0 (`>=0.11.0` in `requirements.txt`)` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-explorer/pyproject.toml` |
| **Repo Imports (1)** | `pathspec (packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `pathspec.PathSpec` | `class` · Init: `(patterns: 'Union[Sequence[TPattern_co], Iterable[TPattern_co]]', *, backend: 'Union[BackendNamesHint, str, None]' = None, _test_backend_factory: '_TestBackendFactoryHint' = None) -> 'None'` · Key attrs: `check_file`, `check_files`, `check_tree_files`, `from_lines`, `match_entries`, `match_file`, `match_files`, `match_tree`<br>The :class:`PathSpec` class is a wrapper around a list of compiled :class:`.Pattern` instances.<br>**Used in:** `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` |

## Public Functions, Classes & Variables

### `pathspec`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class GitIgnoreSpec`** | `class` · Init: `(patterns: 'Union[Sequence[TPattern_co], Iterable[TPattern_co]]', *, backend: 'Union[BackendNamesHint, str, None]' = None, _test_backend_factory: '_TestBackendFactoryHint' = None) -> 'None'` · Attrs: `check_file`, `check_files`, `check_tree_files`, `from_lines`, `match_entries`, `match_file`, `match_files`, `match_tree`, `match_tree_entries`, `match_tree_files` · Methods: `check_file(self, file: 'TStrPath', separators: 'Optional[Collection[str]]' = None) -> 'CheckResult[TStrPath]'`, `check_files(self, files: 'Iterable[TStrPath]', separators: 'Optional[Collection[str]]' = None) -> 'Iterator[CheckResult[TStrPath]]'`, `check_tree_files(self, root: 'StrPath', on_error: 'Optional[Callable[[OSError], None]]' = None, follow_links: 'Optional[bool]' = None) -> 'Iterator[CheckResult[str]]'`, `from_lines(lines: 'Iterable[AnyStr]', pattern_factory: 'Union[str, type[Pattern], Callable[[AnyStr], Pattern], None]' = None, *, backend: 'Union[BackendNamesHint, str, None]' = None, _test_backend_factory: '_TestBackendFactoryHint' = None) -> 'Self'`, `match_entries(self, entries: 'Iterable[TreeEntry]', separators: 'Optional[Collection[str]]' = None, *, negate: 'Optional[bool]' = None) -> 'Iterator[TreeEntry]'`, `match_file(self, file: 'StrPath', separators: 'Optional[Collection[str]]' = None) -> 'bool'`<br>The :class:`GitIgnoreSpec` class extends :class:`.PathSpec` to replicate *gitignore* behavior. This is uses :class:`.GitIgnoreSpecPattern` to fully replicate Git's handling. |
| **`class PathSpec`** | `class` · Init: `(patterns: 'Union[Sequence[TPattern_co], Iterable[TPattern_co]]', *, backend: 'Union[BackendNamesHint, str, None]' = None, _test_backend_factory: '_TestBackendFactoryHint' = None) -> 'None'` · Attrs: `check_file`, `check_files`, `check_tree_files`, `from_lines`, `match_entries`, `match_file`, `match_files`, `match_tree`, `match_tree_entries`, `match_tree_files` · Methods: `check_file(self, file: 'TStrPath', separators: 'Optional[Collection[str]]' = None) -> 'CheckResult[TStrPath]'`, `check_files(self, files: 'Iterable[TStrPath]', separators: 'Optional[Collection[str]]' = None) -> 'Iterator[CheckResult[TStrPath]]'`, `check_tree_files(self, root: 'StrPath', on_error: 'Optional[Callable[[OSError], None]]' = None, follow_links: 'Optional[bool]' = None) -> 'Iterator[CheckResult[str]]'`, `from_lines(pattern_factory: 'Union[str, type[Pattern], Callable[[AnyStr], Pattern]]', lines: 'Iterable[AnyStr]', *, backend: 'Union[BackendNamesHint, str, None]' = None, _test_backend_factory: '_TestBackendFactoryHint' = None) -> 'Self'`, `match_entries(self, entries: 'Iterable[TreeEntry]', separators: 'Optional[Collection[str]]' = None, *, negate: 'Optional[bool]' = None) -> 'Iterator[TreeEntry]'`, `match_file(self, file: 'StrPath', separators: 'Optional[Collection[str]]' = None) -> 'bool'`<br>The :class:`PathSpec` class is a wrapper around a list of compiled :class:`.Pattern` instances. |
| **`class Pattern`** | `class` · Init: `(include: 'Optional[bool]') -> 'None'` · Attrs: `include`, `match`, `match_file` · Methods: `match(self, files: 'Iterable[str]') -> 'Iterator[str]'`, `match_file(self, file: 'str') -> 'Optional[Any]'`<br>The :class:`Pattern` class is the abstract definition of a pattern. |
| **`class RecursionError`** | `class` · Init: `(real_path: 'str', first_path: 'str', second_path: 'str') -> 'None'` · Attrs: `add_note`, `args`, `first_path`, `message`, `real_path`, `second_path`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>The :exc:`RecursionError` exception is raised when recursion is detected. |
| **`class RegexPattern`** | `class` · Init: `(pattern: 'Union[AnyStr, re.Pattern, None]', include: 'Optional[bool]' = None) -> 'None'` · Attrs: `include`, `match`, `match_file`, `pattern`, `pattern_to_regex`, `regex` · Methods: `match(self, files: 'Iterable[str]') -> 'Iterator[str]'`, `match_file(self, file: 'AnyStr') -> 'Optional[RegexMatchResult]'`, `pattern_to_regex(pattern: 'AnyStr') -> 'tuple[Optional[AnyStr], Optional[bool]]'`<br>The :class:`RegexPattern` class is an implementation of a pattern using regular expressions. |
| `__author__` | `variable` · Type: `str` · Value: `'Caleb P. Burns'` |
| `__copyright__` | `variable` · Type: `str` · Value: `'Copyright © 2013-2026 Caleb P. Burns'` |
| `__credits__` | `variable` · Type: `list` · Value: `['Hong Minhee <https://github.com/dahlia>', 'Brandon High...` |
| `__license__` | `variable` · Type: `str` · Value: `'MPL 2.0'` |
| `__version__` | `variable` · Type: `str` · Value: `'1.1.1'` |
| `lookup_pattern()` | `function` · Signature: `(name: 'str') -> 'Callable[[AnyStr], Pattern]'`<br>Looks up a registered pattern factory by name. |
