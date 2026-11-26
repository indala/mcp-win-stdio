# `rapidfuzz` (>=3.0.0)

> High-speed fuzzy string matching for Excel key reconciliation and Explorer typo-tolerant file search.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=3.0.0` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-excel/pyproject.toml`, `packages/mcp-win-stdio-explorer/pyproject.toml` |
| **Repo Imports (2)** | `from rapidfuzz import fuzz (packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py)`; `from rapidfuzz import fuzz, process (packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `rapidfuzz.fuzz` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py`, `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` |
| `rapidfuzz.fuzz.WRatio` | `function` · Params: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Calculates a weighted ratio based on the other ratio algorithms<br>**Used in:** `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` |
| `rapidfuzz.fuzz.token_sort_ratio` | `function` · Params: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Sorts the words in the strings and calculates the fuzz.ratio between them<br>**Used in:** `packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py` |
| `rapidfuzz.process` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` |
| `rapidfuzz.process.extract` | `function` · Params: `(query, choices, *, scorer=<cyfunction WRatio at 0x000001A4FFF08050>, processor=None, limit=5, score_cutoff=None, score_hint=None, scorer_kwargs=None)`<br>Find the best matches in a list of choices. The list is sorted by the similarity. When multiple choices have the same similarity, they are sorted by their index<br>**Used in:** `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` |

## Public Functions, Classes & Variables

### `rapidfuzz`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `get_include()` | `function` · Signature: `() -> 'str'`<br>Return the directory that contains the RapidFuzz \*.h header files. Extension modules that need to compile against RapidFuzz should use this function to locate the appropriate include directory. Notes |

### `rapidfuzz.fuzz`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `QRatio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Calculates a quick ratio between two strings using fuzz.ratio. |
| `WRatio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Calculates a weighted ratio based on the other ratio algorithms |
| `partial_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Searches for the optimal alignment of the shorter string in the longer string and returns the fuzz.ratio for this alignment. |
| `partial_ratio_alignment()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Public function/callable. |
| `partial_token_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Helper method that returns the maximum of fuzz.partial_token_set_ratio and fuzz.partial_token_sort_ratio (faster than manually executing the two functions) |
| `partial_token_set_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Compares the words in the strings based on unique and common words between them using fuzz.partial_ratio |
| `partial_token_sort_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>sorts the words in the strings and calculates the fuzz.partial_ratio between them |
| `ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Calculates the normalized Indel similarity. |
| `token_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Helper method that returns the maximum of fuzz.token_set_ratio and fuzz.token_sort_ratio (faster than manually executing the two functions) |
| `token_set_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Compares the words in the strings based on unique and common words between them using fuzz.ratio |
| `token_sort_ratio()` | `function` · Signature: `(s1, s2, *, processor=None, score_cutoff=None)`<br>Sorts the words in the strings and calculates the fuzz.ratio between them |

### `rapidfuzz.process`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `cdist()` | `function` · Signature: `(queries, choices, *, scorer=<cyfunction ratio at 0x000001A4FFE417F0>, processor=None, score_cutoff=None, score_hint=None, score_multiplier=1, dtype=None, workers=1, **kwargs)`<br>Compute distance/similarity between each pair of the two collections of inputs. |
| `cpdist()` | `function` · Signature: `(queries, choices, *, scorer=<cyfunction ratio at 0x000001A4FFE417F0>, processor=None, score_cutoff=None, score_hint=None, score_multiplier=1, dtype=None, workers=1, **kwargs)`<br>Compute the pairwise distance/similarity between corresponding elements of the queries & choices. |
| `extract()` | `function` · Signature: `(query, choices, *, scorer=<cyfunction WRatio at 0x000001A4FFF08050>, processor=None, limit=5, score_cutoff=None, score_hint=None, scorer_kwargs=None)`<br>Find the best matches in a list of choices. The list is sorted by the similarity. When multiple choices have the same similarity, they are sorted by their index |
| `extractOne()` | `function` · Signature: `(query, choices, *, scorer=<cyfunction WRatio at 0x000001A4FFF08050>, processor=None, score_cutoff=None, score_hint=None, scorer_kwargs=None)`<br>Find the best match in a list of choices. When multiple elements have the same similarity, the first element is returned. |
| `extract_iter()` | `function` · Signature: `(query, choices, *, scorer=<cyfunction WRatio at 0x000001A4FFF08050>, processor=None, score_cutoff=None, score_hint=None, scorer_kwargs=None)`<br>Find the best match in a list of choices |
