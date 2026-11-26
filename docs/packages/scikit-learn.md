# `scikit-learn` (Optional (`sklearn`))

> Optional TF-IDF vectorization (`TfidfVectorizer`) and `cosine_similarity` scoring in RAG hybrid search.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Optional / Transitive Runtime |
| **Version Constraint** | `Optional (`sklearn`)` |
| **Declared / Referenced In** | `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py`, `src/mcp_win_stdio/cli.py` |
| **Repo Imports (2)** | `from sklearn.feature_extraction.text import TfidfVectorizer (packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py)`; `from sklearn.metrics.pairwise import cosine_similarity (packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `sklearn.feature_extraction.text.TfidfVectorizer` | `class` · Init: `(*, input='content', encoding='utf-8', decode_error='strict', strip_accents=None, lowercase=True, preprocessor=None, tokenizer=None, analyzer='word', stop_words=None, token_pattern='(?u)\\b\\w\\w+\\b', ngram_range=(1, 1), max_df=1.0, min_df=1, max_features=None, vocabulary=None, binary=False, dtype=<class 'numpy.float64'>, norm='l2', use_idf=True, smooth_idf=True, sublinear_tf=False)` · Key attrs: `build_analyzer`, `build_preprocessor`, `build_tokenizer`, `decode`, `fit`, `fit_transform`, `get_feature_names_out`, `get_metadata_routing`<br>Convert a collection of raw documents to a matrix of TF-IDF features.<br>**Used in:** `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py` |
| `sklearn.metrics.pairwise.cosine_similarity` | `function` · Params: `(X, Y=None, dense_output=True)`<br>Compute cosine similarity between samples in X and Y.<br>**Used in:** `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py` |

## Public Functions, Classes & Variables

### `sklearn.feature_extraction.text`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class CountVectorizer`** | `class` · Init: `(*, input='content', encoding='utf-8', decode_error='strict', strip_accents=None, lowercase=True, preprocessor=None, tokenizer=None, stop_words=None, token_pattern='(?u)\\b\\w\\w+\\b', ngram_range=(1, 1), analyzer='word', max_df=1.0, min_df=1, max_features=None, vocabulary=None, binary=False, dtype=<class 'numpy.int64'>)` · Attrs: `build_analyzer`, `build_preprocessor`, `build_tokenizer`, `decode`, `fit`, `fit_transform`, `get_feature_names_out`, `get_metadata_routing`, `get_params`, `get_stop_words` · Methods: `build_analyzer(self)`, `build_preprocessor(self)`, `build_tokenizer(self)`, `decode(self, doc)`, `fit(self, raw_documents, y=None)`, `fit_transform(self, raw_documents, y=None)`<br>Convert a collection of text documents to a matrix of token counts. |
| `ENGLISH_STOP_WORDS` | `variable` · Type: `frozenset` · Value: `frozenset({'thus', 'its', 'to', 'thereafter', 'they', 'on...` |
| **`class HashingVectorizer`** | `class` · Init: `(*, input='content', encoding='utf-8', decode_error='strict', strip_accents=None, lowercase=True, preprocessor=None, tokenizer=None, stop_words=None, token_pattern='(?u)\\b\\w\\w+\\b', ngram_range=(1, 1), analyzer='word', n_features=1048576, binary=False, norm='l2', alternate_sign=True, dtype=<class 'numpy.float64'>)` · Attrs: `build_analyzer`, `build_preprocessor`, `build_tokenizer`, `decode`, `fit`, `fit_transform`, `get_metadata_routing`, `get_params`, `get_stop_words`, `partial_fit` · Methods: `build_analyzer(self)`, `build_preprocessor(self)`, `build_tokenizer(self)`, `decode(self, doc)`, `fit(self, X, y=None)`, `fit_transform(self, X, y=None)`<br>Convert a collection of text documents to a matrix of token occurrences. |
| **`class TfidfTransformer`** | `class` · Init: `(*, norm='l2', use_idf=True, smooth_idf=True, sublinear_tf=False)` · Attrs: `fit`, `fit_transform`, `get_feature_names_out`, `get_metadata_routing`, `get_params`, `set_output`, `set_params`, `set_transform_request`, `transform` · Methods: `fit(self, X, y=None)`, `fit_transform(self, X, y=None, **fit_params)`, `get_feature_names_out(self, input_features=None)`, `get_metadata_routing(self)`, `get_params(self, deep=True)`, `set_output(self, *, transform=None)`<br>Transform a count matrix to a normalized tf or tf-idf representation. |
| **`class TfidfVectorizer`** | `class` · Init: `(*, input='content', encoding='utf-8', decode_error='strict', strip_accents=None, lowercase=True, preprocessor=None, tokenizer=None, analyzer='word', stop_words=None, token_pattern='(?u)\\b\\w\\w+\\b', ngram_range=(1, 1), max_df=1.0, min_df=1, max_features=None, vocabulary=None, binary=False, dtype=<class 'numpy.float64'>, norm='l2', use_idf=True, smooth_idf=True, sublinear_tf=False)` · Attrs: `build_analyzer`, `build_preprocessor`, `build_tokenizer`, `decode`, `fit`, `fit_transform`, `get_feature_names_out`, `get_metadata_routing`, `get_params`, `get_stop_words` · Methods: `build_analyzer(self)`, `build_preprocessor(self)`, `build_tokenizer(self)`, `decode(self, doc)`, `fit(self, raw_documents, y=None)`, `fit_transform(self, raw_documents, y=None)`<br>Convert a collection of raw documents to a matrix of TF-IDF features. |
| `strip_accents_ascii()` | `function` · Signature: `(s)`<br>Transform accentuated unicode symbols into ascii or nothing. |
| `strip_accents_unicode()` | `function` · Signature: `(s)`<br>Transform accentuated unicode symbols into their simple counterpart. |
| `strip_tags()` | `function` · Signature: `(s)`<br>Basic regexp based HTML / XML tag stripper function. |

### `sklearn.metrics.pairwise`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class ArgKmin`** | `class` · Init: `()` · Attrs: `compute`, `is_usable_for`, `valid_metrics` · Methods: `compute(X, Y, k, metric='euclidean', chunk_size=None, metric_kwargs=None, strategy=None, return_distance=False)`, `is_usable_for(X, Y, metric) -> bool`, `valid_metrics() -> List[str]`<br>Compute the argkmin of row vectors of X on the ones of Y. |
| **`class DataConversionWarning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Warning used to notify implicit data conversions happening in the code. |
| **`class Hidden`** | `class` · Init: `(constraint)`<br>Class encapsulating a constraint not meant to be exposed to the user. |
| **`class Interval`** | `class` · Init: `(type, left, right, *, closed)` · Attrs: `is_satisfied_by` · Methods: `is_satisfied_by(self, val)`<br>Constraint representing a typed interval. |
| `KERNEL_PARAMS` | `variable` · Type: `dict` · Value: `{'additive_chi2': (), 'chi2': frozenset({'gamma'}), 'cosi...` |
| **`class MissingValues`** | `class` · Init: `(numeric_only=False)` · Attrs: `is_satisfied_by` · Methods: `is_satisfied_by(self, val)`<br>Helper constraint for the `missing_values` parameters. |
| **`class Options`** | `class` · Init: `(type, options, *, deprecated=None)` · Attrs: `is_satisfied_by` · Methods: `is_satisfied_by(self, val)`<br>Constraint representing a finite set of instances of a given type. |
| `PAIRED_DISTANCES` | `variable` · Type: `dict` · Value: `{'cosine': <function paired_cosine_distances at 0x000001A...` |
| `PAIRWISE_BOOLEAN_FUNCTIONS` | `variable` · Type: `list` · Value: `['dice', 'jaccard', 'rogerstanimoto', 'russellrao', 'soka...` |
| `PAIRWISE_DISTANCE_FUNCTIONS` | `variable` · Type: `dict` · Value: `{'cityblock': <function manhattan_distances at 0x000001A4...` |
| `PAIRWISE_KERNEL_FUNCTIONS` | `variable` · Type: `dict` · Value: `{'additive_chi2': <function additive_chi2_kernel at 0x000...` |
| **`class Parallel`** | `class` · Init: `(n_jobs=default(None), backend=default(None), return_as='list', verbose=default(0), timeout=None, pre_dispatch='2 * n_jobs', batch_size='auto', temp_folder=default(None), max_nbytes=default('1M'), mmap_mode=default('r'), prefer=default(None), require=default(None), **backend_kwargs)` · Attrs: `debug`, `dispatch_next`, `dispatch_one_batch`, `format`, `info`, `print_progress`, `warn` · Methods: `debug(self, msg)`, `dispatch_next(self)`, `dispatch_one_batch(self, iterator)`, `format(self, obj, indent=0)`, `info(self, msg)`, `print_progress(self)`<br>Tweak of :class:`joblib.Parallel` that propagates the scikit-learn configuration. |
| **`class StrOptions`** | `class` · Init: `(options, *, deprecated=None)` · Attrs: `is_satisfied_by` · Methods: `is_satisfied_by(self, val)`<br>Constraint representing a finite set of strings. |
| `additive_chi2_kernel()` | `function` · Signature: `(X, Y=None)`<br>Compute the additive chi-squared kernel between observations in X and Y. |
| `check_array()` | `function` · Signature: `(array, accept_sparse=False, *, accept_large_sparse=True, dtype='numeric', order=None, copy=False, force_writeable=False, ensure_all_finite=True, ensure_non_negative=False, ensure_2d=True, allow_nd=False, ensure_min_samples=1, ensure_min_features=1, estimator=None, input_name='')`<br>Input validation on an array, list, sparse matrix or similar. |
| `check_non_negative()` | `function` · Signature: `(X, whom)`<br>Check if there is any negative value in an array. |
| `check_paired_arrays()` | `function` · Signature: `(X, Y)`<br>Set X and Y appropriately and checks inputs for paired distances. |
| `check_pairwise_arrays()` | `function` · Signature: `(X, Y, *, precomputed=False, dtype='infer_float', accept_sparse='csr', ensure_all_finite=True, ensure_2d=True, copy=False)`<br>Set X and Y appropriately and checks inputs. |
| `chi2_kernel()` | `function` · Signature: `(X, Y=None, gamma=1.0)`<br>Compute the exponential chi-squared kernel between X and Y. |
| `config_context()` | `function` · Signature: `(*, assume_finite=None, working_memory=None, print_changed_only=None, display=None, pairwise_dist_chunk_size=None, enable_cython_pairwise_dist=None, array_api_dispatch=None, transform_output=None, enable_metadata_routing=None, skip_parameter_validation=None, sparse_interface=None)`<br>Context manager to temporarily change the global scikit-learn configuration. |
| `cosine_distances()` | `function` · Signature: `(X, Y=None)`<br>Compute cosine distance between samples in X and Y. |
| `cosine_similarity()` | `function` · Signature: `(X, Y=None, dense_output=True)`<br>Compute cosine similarity between samples in X and Y. |
| `delayed()` | `function` · Signature: `(function)`<br>Decorator used to capture the arguments of a function. |
| `distance_metrics()` | `function` · Signature: `()`<br>Valid metrics for pairwise_distances. |
| `euclidean_distances()` | `function` · Signature: `(X, Y=None, *, Y_norm_squared=None, squared=False, X_norm_squared=None)`<br>Compute the distance matrix between each pair from a feature array X and Y. |
| `gen_batches()` | `function` · Signature: `(n, batch_size, *, min_batch_size=0)`<br>Generator to create slices containing `batch_size` elements from 0 to `n`. |
| `gen_even_slices()` | `function` · Signature: `(n, n_packs, *, n_samples=None)`<br>Generator to create `n_packs` evenly spaced slices going up to `n`. |
| `get_chunk_n_rows()` | `function` · Signature: `(row_bytes, *, max_n_rows=None, working_memory=None)`<br>Calculate how many rows can be processed within `working_memory`. |
| `get_namespace()` | `function` · Signature: `(*arrays, remove_none=True, remove_types=(<class 'str'>, <class 'list'>, <class 'tuple'>), xp=None)`<br>Get namespace of arrays. |
| `get_namespace_and_device()` | `function` · Signature: `(*array_list, remove_none=True, remove_types=(<class 'str'>, <class 'list'>, <class 'tuple'>), xp=None)`<br>Combination into one single function of `get_namespace` and `device`. |
| `haversine_distances()` | `function` · Signature: `(X, Y=None)`<br>Compute the Haversine distance between samples in X and Y. |
| `is_scalar_nan()` | `function` · Signature: `(x)`<br>Test if x is NaN. |
| `kernel_metrics()` | `function` · Signature: `()`<br>Valid metrics for pairwise_kernels. |
| `laplacian_kernel()` | `function` · Signature: `(X, Y=None, gamma=None)`<br>Compute the laplacian kernel between X and Y. |
| `linear_kernel()` | `function` · Signature: `(X, Y=None, dense_output=True)`<br>Compute the linear kernel between X and Y. |
| `manhattan_distances()` | `function` · Signature: `(X, Y=None)`<br>Compute the L1 distances between the vectors in X and Y. |
| `nan_euclidean_distances()` | `function` · Signature: `(X, Y=None, *, squared=False, missing_values=nan, copy=True)`<br>Calculate the euclidean distances in the presence of missing values. |
| `normalize()` | `function` · Signature: `(X, norm='l2', *, axis=1, copy=True, return_norm=False)`<br>Scale input vectors individually to unit norm (vector length). |
| `paired_cosine_distances()` | `function` · Signature: `(X, Y)`<br>Compute the paired cosine distances between X and Y. |
| `paired_distances()` | `function` · Signature: `(X, Y, *, metric='euclidean', **kwds)`<br>Compute the paired distances between X and Y. |
| `paired_euclidean_distances()` | `function` · Signature: `(X, Y)`<br>Compute the paired euclidean distances between X and Y. |
| `paired_manhattan_distances()` | `function` · Signature: `(X, Y)`<br>Compute the paired L1 distances between X and Y. |
| `pairwise_distances()` | `function` · Signature: `(X, Y=None, metric='euclidean', *, n_jobs=None, ensure_all_finite=True, **kwds)`<br>Compute the distance matrix from a feature array X and optional Y. |
| `pairwise_distances_argmin()` | `function` · Signature: `(X, Y, *, axis=1, metric='euclidean', metric_kwargs=None)`<br>Compute minimum distances between one point and a set of points. |
| `pairwise_distances_argmin_min()` | `function` · Signature: `(X, Y, *, axis=1, metric='euclidean', metric_kwargs=None)`<br>Compute minimum distances between one point and a set of points. |
| `pairwise_distances_chunked()` | `function` · Signature: `(X, Y=None, *, reduce_func=None, metric='euclidean', n_jobs=None, working_memory=None, **kwds)`<br>Generate a distance matrix chunk by chunk with optional reduction. |
| `pairwise_kernels()` | `function` · Signature: `(X, Y=None, metric='linear', *, filter_params=False, n_jobs=None, **kwds)`<br>Compute the kernel between arrays X and optional array Y. |
| `parse_version()` | `function` · Signature: `(version: str) -> ForwardRef('LegacyVersion') \| ForwardRef('Version')`<br>Parse the given version from a string to an appropriate class. |
| `polynomial_kernel()` | `function` · Signature: `(X, Y=None, degree=3, gamma=None, coef0=1)`<br>Compute the polynomial kernel between X and Y. |
| `rbf_kernel()` | `function` · Signature: `(X, Y=None, gamma=None)`<br>Compute the rbf (gaussian) kernel between X and Y. |
| `row_norms()` | `function` · Signature: `(X, squared=False)`<br>Row-wise (squared) Euclidean norm of X. |
| `safe_sparse_dot()` | `function` · Signature: `(a, b, *, dense_output=False)`<br>Dot product that handle the sparse matrix case correctly. |
| `sigmoid_kernel()` | `function` · Signature: `(X, Y=None, gamma=None, coef0=1)`<br>Compute the sigmoid kernel between X and Y. |
| `sp_base_version` | `variable` · Type: `Version` · Value: `<Version('1.18.1')>` |
| `validate_params()` | `function` · Signature: `(parameter_constraints, *, prefer_skip_nested_validation)`<br>Decorator to validate types and values of functions and methods. |
