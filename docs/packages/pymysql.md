# `pymysql` (>=1.1.0)

> Pure-Python MySQL / MariaDB client driver and `DictCursor` support.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=1.1.0` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-db/pyproject.toml` |
| **Repo Imports (4)** | `from pymysql.cursors import DictCursor (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)`; `pymysql (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)`; `pymysql (src/mcp_win_stdio/core/wizard.py)`; `pymysql.cursors (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `pymysql.MySQLError` | `class` · Init: `(...)` · Key attrs: `add_note`, `args`, `with_traceback`<br>Exception related to operation with MySQL.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `pymysql.connect` | `class` · Init: `(*, user=None, password='', host=None, database=None, unix_socket=None, port=0, charset='', collation=None, sql_mode=None, read_default_file=None, conv=None, use_unicode=True, client_flag=0, cursorclass=<class 'pymysql.cursors.Cursor'>, init_command=None, connect_timeout=10, read_default_group=None, autocommit=False, local_infile=False, max_allowed_packet=16777216, defer_connect=False, auth_plugin_map=None, read_timeout=None, write_timeout=None, bind_address=None, binary_prefix=False, program_name=None, server_public_key=None, ssl=None, ssl_ca=None, ssl_cert=None, ssl_disabled=None, ssl_key=None, ssl_key_password=None, ssl_verify_cert=None, ssl_verify_identity=None, compress=None, named_pipe=None, passwd=None, db=None)` · Key attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`<br>Representation of a socket with a mysql server.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py`, `src/mcp_win_stdio/core/wizard.py` |
| `pymysql.constants` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `pymysql.cursors` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `pymysql.cursors.DictCursor` | `class` · Init: `(connection)` · Key attrs: `callproc`, `close`, `dict_type`, `execute`, `executemany`, `fetchall`, `fetchmany`, `fetchone`<br>A cursor which returns results as a dictionary<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |

## Public Functions, Classes & Variables

### `pymysql`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `BINARY` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({249, 250, 251, 252})` |
| `Binary()` | `function` · Signature: `(x)`<br>Return x as a binary type. |
| **`class Connect`** | `class` · Init: `(*, user=None, password='', host=None, database=None, unix_socket=None, port=0, charset='', collation=None, sql_mode=None, read_default_file=None, conv=None, use_unicode=True, client_flag=0, cursorclass=<class 'pymysql.cursors.Cursor'>, init_command=None, connect_timeout=10, read_default_group=None, autocommit=False, local_infile=False, max_allowed_packet=16777216, defer_connect=False, auth_plugin_map=None, read_timeout=None, write_timeout=None, bind_address=None, binary_prefix=False, program_name=None, server_public_key=None, ssl=None, ssl_ca=None, ssl_cert=None, ssl_disabled=None, ssl_key=None, ssl_key_password=None, ssl_verify_cert=None, ssl_verify_identity=None, compress=None, named_pipe=None, passwd=None, db=None)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `DataError(*args, sqlstate=None)`, `DatabaseError(*args, sqlstate=None)`, `Error(*args, sqlstate=None)`, `IntegrityError(*args, sqlstate=None)`, `InterfaceError(*args, sqlstate=None)`, `InternalError(*args, sqlstate=None)`<br>Representation of a socket with a mysql server. |
| **`class Connection`** | `class` · Init: `(*, user=None, password='', host=None, database=None, unix_socket=None, port=0, charset='', collation=None, sql_mode=None, read_default_file=None, conv=None, use_unicode=True, client_flag=0, cursorclass=<class 'pymysql.cursors.Cursor'>, init_command=None, connect_timeout=10, read_default_group=None, autocommit=False, local_infile=False, max_allowed_packet=16777216, defer_connect=False, auth_plugin_map=None, read_timeout=None, write_timeout=None, bind_address=None, binary_prefix=False, program_name=None, server_public_key=None, ssl=None, ssl_ca=None, ssl_cert=None, ssl_disabled=None, ssl_key=None, ssl_key_password=None, ssl_verify_cert=None, ssl_verify_identity=None, compress=None, named_pipe=None, passwd=None, db=None)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `DataError(*args, sqlstate=None)`, `DatabaseError(*args, sqlstate=None)`, `Error(*args, sqlstate=None)`, `IntegrityError(*args, sqlstate=None)`, `InterfaceError(*args, sqlstate=None)`, `InternalError(*args, sqlstate=None)`<br>Representation of a socket with a mysql server. |
| `DATE` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({10, 14})` |
| **`class DBAPISet`** | `class` · Init: `(iterable=(), /)` · Attrs: `copy`, `difference`, `intersection`, `isdisjoint`, `issubset`, `issuperset`, `symmetric_difference`, `union` · Methods: `copy(self, /)`, `difference(self, /, *others)`, `intersection(self, /, *others)`, `isdisjoint(self, other, /)`, `issubset(self, other, /)`, `issuperset(self, other, /)`<br>Build an immutable unordered collection of unique elements. |
| **`class DataError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for errors that are due to problems with the processed data like division by zero, numeric value out of range, etc. |
| **`class DatabaseError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for errors that are related to the database. |
| `DateFromTicks()` | `function` · Signature: `(ticks)`<br>Public function/callable. |
| **`class Error`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception that is the base class of all other error exceptions (not Warning). |
| **`class IntegrityError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when the relational integrity of the database is affected, e.g. a foreign key check fails, duplicate key, etc. |
| **`class InterfaceError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for errors that are related to the database interface rather than the database itself. |
| **`class InternalError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when the database encounters an internal error, e.g. the cursor is not valid anymore, the transaction is out of sync, etc. |
| **`class MySQLError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception related to operation with MySQL. |
| `NULL` | `variable` · Type: `str` · Value: `'NULL'` |
| `NUMBER` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({0, 1, 3, 4, 5, 8, 9, 13})` |
| **`class NotSupportedError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised in case a method or database API was used which is not supported by the database, e.g. requesting a .rollback() on a connection that does not support transaction or has transactions turned off. |
| **`class OperationalError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for errors that are related to the database's operation and not necessarily under the control of the programmer, e.g. an unexpected disconnect occurs, the data source name is not found, a transaction could not be processed,... |
| **`class ProgrammingError`** | `class` · Init: `(*args, sqlstate=None)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for programming errors, e.g. table not found or already exists, syntax error in the SQL statement, wrong number of parameters specified, etc. |
| `ROWID` | `variable` · Type: `DBAPISet` · Value: `DBAPISet()` |
| `STRING` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({253, 254, 247})` |
| `TIME` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({11})` |
| `TIMESTAMP` | `variable` · Type: `DBAPISet` · Value: `DBAPISet({12, 7})` |
| `TimeFromTicks()` | `function` · Signature: `(ticks)`<br>Public function/callable. |
| `TimestampFromTicks()` | `function` · Signature: `(ticks)`<br>Public function/callable. |
| **`class Warning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised for important warnings like data truncations while inserting, etc. |
| `__version__` | `variable` · Type: `str` · Value: `'2.2.8'` |
| `apilevel` | `variable` · Type: `str` · Value: `'2.0'` |
| **`class connect`** | `class` · Init: `(*, user=None, password='', host=None, database=None, unix_socket=None, port=0, charset='', collation=None, sql_mode=None, read_default_file=None, conv=None, use_unicode=True, client_flag=0, cursorclass=<class 'pymysql.cursors.Cursor'>, init_command=None, connect_timeout=10, read_default_group=None, autocommit=False, local_infile=False, max_allowed_packet=16777216, defer_connect=False, auth_plugin_map=None, read_timeout=None, write_timeout=None, bind_address=None, binary_prefix=False, program_name=None, server_public_key=None, ssl=None, ssl_ca=None, ssl_cert=None, ssl_disabled=None, ssl_key=None, ssl_key_password=None, ssl_verify_cert=None, ssl_verify_identity=None, compress=None, named_pipe=None, passwd=None, db=None)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `DataError(*args, sqlstate=None)`, `DatabaseError(*args, sqlstate=None)`, `Error(*args, sqlstate=None)`, `IntegrityError(*args, sqlstate=None)`, `InterfaceError(*args, sqlstate=None)`, `InternalError(*args, sqlstate=None)`<br>Representation of a socket with a mysql server. |
| `get_client_info()` | `function` · Signature: `()`<br>Public function/callable. |
| `install_as_MySQLdb()` | `function` · Signature: `()`<br>After this function is called, any application that imports MySQLdb will unwittingly actually use pymysql. |
| `paramstyle` | `variable` · Type: `str` · Value: `'pyformat'` |
| `threadsafety` | `variable` · Type: `int` · Value: `1` |
| `version_info` | `variable` · Type: `tuple` · Value: `(2, 2, 8, 'final', 1)` |

### `pymysql.cursors`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class Cursor`** | `class` · Init: `(connection)` · Attrs: `callproc`, `close`, `execute`, `executemany`, `fetchall`, `fetchmany`, `fetchone`, `max_stmt_length`, `mogrify`, `nextset` · Methods: `callproc(self, procname, args=())`, `close(self)`, `execute(self, query, args=None)`, `executemany(self, query, args)`, `fetchall(self)`, `fetchmany(self, size=None)`<br>This is the object used to interact with the database. |
| **`class DictCursor`** | `class` · Init: `(connection)` · Attrs: `callproc`, `close`, `dict_type`, `execute`, `executemany`, `fetchall`, `fetchmany`, `fetchone`, `max_stmt_length`, `mogrify` · Methods: `callproc(self, procname, args=())`, `close(self)`, `dict_type(...)`, `execute(self, query, args=None)`, `executemany(self, query, args)`, `fetchall(self)`<br>A cursor which returns results as a dictionary |
| **`class DictCursorMixin`** | `class` · Init: `()` · Attrs: `dict_type` · Methods: `dict_type(...)`<br>Public class. |
| `RE_INSERT_VALUES` | `variable` · Type: `Pattern` · Value: `re.compile('\\s*((?:INSERT\|REPLACE)\\b.+\\bVALUES?\\s*)(\...` |
| **`class SSCursor`** | `class` · Init: `(connection)` · Attrs: `callproc`, `close`, `execute`, `executemany`, `fetchall`, `fetchall_unbuffered`, `fetchmany`, `fetchone`, `max_stmt_length`, `mogrify` · Methods: `callproc(self, procname, args=())`, `close(self)`, `execute(self, query, args=None)`, `executemany(self, query, args)`, `fetchall(self)`, `fetchall_unbuffered(self)`<br>Unbuffered Cursor, mainly useful for queries that return a lot of data, or for connections to remote servers over a slow network. |
| **`class SSDictCursor`** | `class` · Init: `(connection)` · Attrs: `callproc`, `close`, `dict_type`, `execute`, `executemany`, `fetchall`, `fetchall_unbuffered`, `fetchmany`, `fetchone`, `max_stmt_length` · Methods: `callproc(self, procname, args=())`, `close(self)`, `dict_type(...)`, `execute(self, query, args=None)`, `executemany(self, query, args)`, `fetchall(self)`<br>An unbuffered cursor, which returns results as a dictionary |
