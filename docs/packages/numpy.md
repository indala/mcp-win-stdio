# `numpy` (>=1.24.0)

> Numerical arrays and vector computations for RAG hybrid search and Excel-DB streaming.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=1.24.0` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-rag/pyproject.toml` |
| **Repo Imports (2)** | `numpy (packages/mcp-win-stdio-excel-db/src/mcp_win_stdio/excel_db/stream.py)`; `numpy (packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `numpy.argsort` | `function` · Params: `(a, axis=-1, kind=None, order=None, *, stable=None, descending=<no value>)`<br>Returns the indices that would sort an array.<br>**Used in:** `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/store.py` |

## Public Functions, Classes & Variables

### `numpy`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `False_` | `variable` · Type: `bool` · Value: `np.False_` |
| `ScalarType` | `variable` · Type: `tuple` · Value: `(<class 'int'>, <class 'float'>, <class 'complex'>, <clas...` |
| `True_` | `variable` · Type: `bool` · Value: `np.True_` |
| **`class __array_namespace_info__`** | `class` · Init: `()` · Attrs: `capabilities`, `default_device`, `default_dtypes`, `devices`, `dtypes` · Methods: `capabilities(self)`, `default_device(self)`, `default_dtypes(self, *, device=None)`, `devices(self)`, `dtypes(self, *, device=None, kind=None)`<br>Get the array API inspection namespace for NumPy. |
| `__version__` | `variable` · Type: `str` · Value: `'2.5.3'` |
| `abs()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>absolute(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `absolute()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>absolute(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `acos()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arccos(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `acosh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arccosh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `add()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>add(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `all()` | `function` · Signature: `(a, axis=None, out=None, keepdims=<no value>, *, where=<no value>)`<br>Test whether all array elements along a given axis evaluate to True. |
| `allclose()` | `function` · Signature: `(a, b, rtol=1e-05, atol=1e-08, equal_nan=False)`<br>Returns True if two arrays are element-wise equal within a tolerance. |
| `amax()` | `function` · Signature: `(a, axis=None, out=None, keepdims=<no value>, initial=<no value>, where=<no value>)`<br>Return the maximum of an array or maximum along an axis. |
| `amin()` | `function` · Signature: `(a, axis=None, out=None, keepdims=<no value>, initial=<no value>, where=<no value>)`<br>Return the minimum of an array or minimum along an axis. |
| `angle()` | `function` · Signature: `(z, deg=False)`<br>Return the angle of the complex argument. |
| `any()` | `function` · Signature: `(a, axis=None, out=None, keepdims=<no value>, *, where=<no value>)`<br>Test whether any array element along a given axis evaluates to True. |
| `append()` | `function` · Signature: `(arr, values, axis=None)`<br>Append values to the end of an array. |
| `apply_along_axis()` | `function` · Signature: `(func1d, axis, arr, *args, **kwargs)`<br>Apply a function to 1-D slices along the given axis. |
| `apply_over_axes()` | `function` · Signature: `(func, a, axes)`<br>Apply a function repeatedly over multiple axes. |
| `arange()` | `function` · Signature: `(start_or_stop, /, stop=None, step=1, *, dtype=None, device=None, like=None)`<br>arange([start,] stop[, step,], dtype=None, *, device=None, like=None) |
| `arccos()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arccos(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arccosh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arccosh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arcsin()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arcsin(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arcsinh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arcsinh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arctan()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctan(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arctan2()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctan2(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `arctanh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctanh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `argmax()` | `function` · Signature: `(a, axis=None, out=None, *, keepdims=<no value>)`<br>Returns the indices of the maximum values along an axis. |
| `argmin()` | `function` · Signature: `(a, axis=None, out=None, *, keepdims=<no value>)`<br>Returns the indices of the minimum values along an axis. |
| `argpartition()` | `function` · Signature: `(a, kth, axis=-1, kind='introselect', order=None)`<br>Perform an indirect partition along the given axis using the algorithm specified by the `kind` keyword. It returns an array of indices of the same shape as `a` that index data along the given axis in partitioned order. |
| `argsort()` | `function` · Signature: `(a, axis=-1, kind=None, order=None, *, stable=None, descending=<no value>)`<br>Returns the indices that would sort an array. |
| `argwhere()` | `function` · Signature: `(a)`<br>Find the indices of array elements that are non-zero, grouped by element. |
| `around()` | `function` · Signature: `(a, decimals=0, out=None)`<br>Round an array to the given number of decimals. |
| `array()` | `function` · Signature: `(object, dtype=None, *, copy=True, order='K', subok=False, ndmin=0, ndmax=0, like=None)`<br>array(object, dtype=None, *, copy=True, order='K', subok=False, ndmin=0, ndmax=0, like=None) |
| `array2string()` | `function` · Signature: `(a, max_line_width=None, precision=None, suppress_small=None, separator=' ', prefix='', *, formatter=None, threshold=None, edgeitems=None, sign=None, floatmode=None, suffix='', legacy=None)`<br>Return a string representation of an array. |
| `array_equal()` | `function` · Signature: `(a1, a2, equal_nan=False)`<br>True if two arrays have the same shape and elements, False otherwise. |
| `array_equiv()` | `function` · Signature: `(a1, a2)`<br>Returns True if input arrays are shape consistent and all elements equal. |
| `array_repr()` | `function` · Signature: `(arr, max_line_width=None, precision=None, suppress_small=None)`<br>Return the string representation of an array. |
| `array_split()` | `function` · Signature: `(ary, indices_or_sections, axis=0)`<br>Split an array into multiple sub-arrays. |
| `array_str()` | `function` · Signature: `(a, max_line_width=None, precision=None, suppress_small=None)`<br>Return a string representation of the data in an array. |
| `asanyarray()` | `function` · Signature: `(a, dtype=None, order=None, *, device=None, copy=None, like=None)`<br>asanyarray(a, dtype=None, order=None, *, device=None, copy=None, like=None) |
| `asarray()` | `function` · Signature: `(a, dtype=None, order=None, *, device=None, copy=None, like=None)`<br>asarray(a, dtype=None, order=None, *, device=None, copy=None, like=None) |
| `asarray_chkfinite()` | `function` · Signature: `(a, dtype=None, order=None)`<br>Convert the input to an array, checking for NaNs or Infs. |
| `ascontiguousarray()` | `function` · Signature: `(a, dtype=None, *, like=None)`<br>ascontiguousarray(a, dtype=None, *, like=None) |
| `asfortranarray()` | `function` · Signature: `(a, dtype=None, *, like=None)`<br>asfortranarray(a, dtype=None, *, like=None) |
| `asin()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arcsin(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `asinh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arcsinh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `asmatrix()` | `function` · Signature: `(data, dtype=None)`<br>Interpret the input as a matrix. |
| `astype()` | `function` · Signature: `(x, dtype, /, *, copy=True, device=None)`<br>Copies an array to a specified data type. |
| `atan()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctan(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `atan2()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctan2(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `atanh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>arctanh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `atleast_1d()` | `function` · Signature: `(*arys)`<br>Convert inputs to arrays with at least one dimension. |
| `atleast_2d()` | `function` · Signature: `(*arys)`<br>View inputs as arrays with at least two dimensions. |
| `atleast_3d()` | `function` · Signature: `(*arys)`<br>View inputs as arrays with at least three dimensions. |
| `average()` | `function` · Signature: `(a, axis=None, weights=None, returned=False, *, keepdims=<no value>)`<br>Compute the weighted average along the specified axis. |
| `bartlett()` | `function` · Signature: `(M)`<br>Return the Bartlett window. |
| `base_repr()` | `function` · Signature: `(number, base=2, padding=0)`<br>Return a string representation of a number in the given base system. |
| `binary_repr()` | `function` · Signature: `(num, width=None)`<br>Return the binary representation of the input number as a string. |
| `bincount()` | `function` · Signature: `(x, /, weights=None, minlength=0)`<br>bincount(x, /, weights=None, minlength=0) |
| `bitwise_and()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>bitwise_and(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_count()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>bitwise_count(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_invert()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>invert(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_left_shift()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>left_shift(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_not()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>invert(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_or()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>bitwise_or(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_right_shift()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>right_shift(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `bitwise_xor()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>bitwise_xor(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `blackman()` | `function` · Signature: `(M)`<br>Return the Blackman window. |
| `block()` | `function` · Signature: `(arrays)`<br>Assemble an nd-array from nested lists of blocks. |
| `bmat()` | `function` · Signature: `(obj, ldict=None, gdict=None)`<br>Build a matrix object from a string, nested sequence, or array. |
| **`class bool`** | `class` · Init: `(value=False, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Boolean type (True or False), stored as a byte. |
| **`class bool_`** | `class` · Init: `(value=False, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Boolean type (True or False), stored as a byte. |
| **`class broadcast`** | `class` · Init: `(*arrays)` · Attrs: `index`, `iters`, `nd`, `ndim`, `numiter`, `reset`, `shape`, `size` · Methods: `reset(self, /)`<br>Produce an object that mimics broadcasting. |
| `broadcast_arrays()` | `function` · Signature: `(*args, subok=False)`<br>Broadcast any number of arrays against each other. |
| `broadcast_shapes()` | `function` · Signature: `(*args)`<br>Broadcast the input shapes into a single shape. |
| `broadcast_to()` | `function` · Signature: `(array, shape, subok=False)`<br>Broadcast an array to a new shape. |
| `busday_count()` | `function` · Signature: `(begindates, enddates, weekmask='1111100', holidays=(), busdaycal=None, out=None)`<br>busday_count( begindates, enddates, weekmask='1111100', holidays=[], busdaycal=None, out=None ) |
| `busday_offset()` | `function` · Signature: `(dates, offsets, roll='raise', weekmask='1111100', holidays=None, busdaycal=None, out=None)`<br>busday_offset( dates, offsets, roll='raise', weekmask='1111100', holidays=None, busdaycal=None, out=None, ) |
| **`class busdaycalendar`** | `class` · Init: `(weekmask='1111100', holidays=None)` · Attrs: `holidays`, `weekmask`<br>busdaycalendar(weekmask='1111100', holidays=None) |
| **`class byte`** | `class` · Init: `(value=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `bit_count`, `byteswap` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Signed integer type, compatible with C ``char``. |
| **`class bytes_`** | `class` · Init: `(value='', /, *args, **kwargs)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `capitalize` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>A byte string. |
| `c_` | `variable` · Type: `CClass` · Value: `<numpy.lib._index_tricks_impl.CClass object at 0x000001A4...` |
| `can_cast()` | `function` · Signature: `(from_, to, casting='safe')`<br>can_cast(from_, to, casting='safe') |
| `cbrt()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>cbrt(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| **`class cdouble`** | `class` · Init: `(real=0, imag=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Complex number type composed of two double-precision floating-point numbers, compatible with Python :class:`complex`. |
| `ceil()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>ceil(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| **`class character`** | `class` · Init: `()` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Abstract base class of all character string scalar types. |
| `choose()` | `function` · Signature: `(a, choices, out=None, mode='raise')`<br>Construct an array from an index array and a list of arrays to choose from. |
| `clip()` | `function` · Signature: `(a, a_min=<no value>, a_max=<no value>, out=None, *, min=<no value>, max=<no value>, **kwargs)`<br>Clip (limit) the values in an array. |
| **`class clongdouble`** | `class` · Init: `(real=0, imag=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Complex number type composed of two extended-precision floating-point numbers. |
| `column_stack()` | `function` · Signature: `(tup)`<br>Stack 1-D arrays as columns into a 2-D array. |
| `common_type()` | `function` · Signature: `(*arrays)`<br>Return a scalar type which is common to the input arrays. |
| **`class complex128`** | `class` · Init: `(real=0, imag=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Complex number type composed of two double-precision floating-point numbers, compatible with Python :class:`complex`. |
| **`class complex64`** | `class` · Init: `(real=0, imag=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Complex number type composed of two single-precision floating-point numbers. |
| **`class complexfloating`** | `class` · Init: `()` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Abstract base class of all complex number scalar types that are made up of floating-point numbers. |
| `compress()` | `function` · Signature: `(condition, a, axis=None, out=None)`<br>Return selected slices of an array along given axis. |
| `concat()` | `function` · Signature: `(arrays, /, axis=0, out=None, *, dtype=None, casting='same_kind')`<br>Join a sequence of arrays along an existing axis. |
| `concatenate()` | `function` · Signature: `(arrays, /, axis=0, out=None, *, dtype=None, casting='same_kind')`<br>Join a sequence of arrays along an existing axis. |
| `conj()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>conjugate(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `conjugate()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>conjugate(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `convolve()` | `function` · Signature: `(a, v, mode='full')`<br>Returns the discrete, linear convolution of two one-dimensional sequences. |
| `copy()` | `function` · Signature: `(a, order='K', subok=False)`<br>Return an array copy of the given object. |
| `copysign()` | `function` · Signature: `(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>copysign(x1, x2, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `copyto()` | `function` · Signature: `(dst, src, casting='same_kind', where=True)`<br>copyto(dst, src, casting='same_kind', where=True) |
| `corrcoef()` | `function` · Signature: `(x, y=None, rowvar=True, *, dtype=None)`<br>Return Pearson product-moment correlation coefficients. |
| `correlate()` | `function` · Signature: `(a, v, mode='valid')`<br>Cross-correlation of two 1-dimensional sequences. |
| `cos()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>cos(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `cosh()` | `function` · Signature: `(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True, signature=None)`<br>cosh(x, /, out=None, *, where=True, casting='same_kind', order='K', dtype=None, subok=True[, signature]) |
| `count_nonzero()` | `function` · Signature: `(a, axis=None, *, keepdims=False)`<br>Counts the number of non-zero values in the array ``a``. |
| `cov()` | `function` · Signature: `(m, y=None, rowvar=True, bias=False, ddof=None, fweights=None, aweights=None, *, dtype=None)`<br>Estimate a covariance matrix, given data and weights. |
| `cross()` | `function` · Signature: `(a, b, axisa=-1, axisb=-1, axisc=-1, axis=None)`<br>Return the cross product of two (arrays of) vectors. |
| **`class csingle`** | `class` · Init: `(real=0, imag=0, /)` · Attrs: `T`, `all`, `any`, `argmax`, `argmin`, `argsort`, `astype`, `base`, `byteswap`, `choose` · Methods: `all(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `any(self, /, axis=None, out=None, keepdims=False, *, where=True)`, `argmax(self, /, axis=None, out=None, *, keepdims=False)`, `argmin(self, /, axis=None, out=None, *, keepdims=False)`, `argsort(self, /, axis=-1, kind=None, order=None, *, stable=None, descending=None)`, `astype(self, /, dtype, order='K', casting='unsafe', subok=True, copy=True)`<br>Complex number type composed of two single-precision floating-point numbers. |
| `cumprod()` | `function` · Signature: `(a, axis=None, dtype=None, out=None)`<br>Return the cumulative product of elements along a given axis. |
| `cumsum()` | `function` · Signature: `(a, axis=None, dtype=None, out=None)`<br>Return the cumulative sum of the elements along a given axis. |
| `cumulative_prod()` | `function` · Signature: `(x, /, *, axis=None, dtype=None, out=None, include_initial=False)`<br>Return the cumulative product of elements along a given axis. |
| `cumulative_sum()` | `function` · Signature: `(x, /, *, axis=None, dtype=None, out=None, include_initial=False)`<br>Return the cumulative sum of the elements along a given axis. |
