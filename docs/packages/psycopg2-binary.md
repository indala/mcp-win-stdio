# `psycopg2-binary` (>=2.9.0)

> PostgreSQL database adapter, dict cursors (`RealDictCursor`), and batch execution (`execute_batch`).

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=2.9.0` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-db/pyproject.toml` |
| **Repo Imports (5)** | `from psycopg2.extras import RealDictCursor (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)`; `from psycopg2.extras import execute_batch (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)`; `psycopg2 (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)`; `psycopg2 (src/mcp_win_stdio/core/wizard.py)`; `psycopg2.extensions (packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `psycopg2.Error` | `class` · Init: `(...)` · Key attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback`<br>Base class for error exceptions.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `psycopg2.connect` | `function` · Params: `(dsn=None, connection_factory=None, cursor_factory=None, **kwargs)`<br>Create a new database connection.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py`, `src/mcp_win_stdio/core/wizard.py` |
| `psycopg2.extensions.cursor` | `class` · Init: `(...)` · Key attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`<br>A database cursor.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `psycopg2.extras.RealDictCursor` | `class` · Init: `(*args, **kwargs)` · Key attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`<br>A cursor that uses a real dict as the base type for rows.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |
| `psycopg2.extras.execute_batch` | `function` · Params: `(cur, sql, argslist, page_size=100)`<br>Execute groups of statements in fewer server roundtrips.<br>**Used in:** `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` |

## Public Functions, Classes & Variables

### `psycopg2`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `BINARY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class Binary`** | `class` · Init: `(...)` · Attrs: `adapted`, `buffer`, `getquoted`, `prepare` · Methods: `getquoted(self, /)`, `prepare(...)`<br>Binary(buffer) -> new binary object |
| `DATETIME()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class DataError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to problems with the processed data. |
| **`class DatabaseError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to the database engine. |
| `Date()` | `function` · Signature: `(...)`<br>Date(year, month, day) -> new date |
| `DateFromTicks()` | `function` · Signature: `(...)`<br>DateFromTicks(ticks) -> new date |
| **`class Error`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Base class for error exceptions. |
| **`class IntegrityError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to database integrity. |
| **`class InterfaceError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to the database interface. |
| **`class InternalError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>The database encountered an internal error. |
| `NUMBER()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class NotSupportedError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>A method or database API was used which is not supported by the database. |
| **`class OperationalError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to database operation (disconnect, memory allocation etc). |
| **`class ProgrammingError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to database programming (SQL error, table not found etc). |
| `ROWID()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `STRING()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `Time()` | `function` · Signature: `(...)`<br>Time(hour, minutes, seconds, tzinfo=None) -> new time |
| `TimeFromTicks()` | `function` · Signature: `(...)`<br>TimeFromTicks(ticks) -> new time |
| `Timestamp()` | `function` · Signature: `(...)`<br>Timestamp(year, month, day, hour, minutes, seconds, tzinfo=None) -> new timestamp |
| `TimestampFromTicks()` | `function` · Signature: `(...)`<br>TimestampFromTicks(ticks) -> new timestamp |
| **`class Warning`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>A database warning. |
| `apilevel` | `variable` · Type: `str` · Value: `'2.0'` |
| `connect()` | `function` · Signature: `(dsn=None, connection_factory=None, cursor_factory=None, **kwargs)`<br>Create a new database connection. |
| `paramstyle` | `variable` · Type: `str` · Value: `'pyformat'` |
| `threadsafety` | `variable` · Type: `int` · Value: `2` |

### `psycopg2.extras`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class CompositeCaster`** | `class` · Init: `(name, oid, attrs, array_oid=None, schema=None)` · Attrs: `make`, `parse`, `tokenize` · Methods: `make(self, values)`, `parse(self, s, curs)`, `tokenize(s)`<br>Helps conversion of a PostgreSQL composite type into a Python object. |
| **`class DateRange`** | `class` · Init: `(lower=None, upper=None, bounds='[)', empty=False)` · Attrs: `isempty`, `lower`, `lower_inc`, `lower_inf`, `upper`, `upper_inc`, `upper_inf`<br>Represents :sql:`daterange` values. |
| **`class DateTimeRange`** | `class` · Init: `(lower=None, upper=None, bounds='[)', empty=False)` · Attrs: `isempty`, `lower`, `lower_inc`, `lower_inf`, `upper`, `upper_inc`, `upper_inf`<br>Represents :sql:`tsrange` values. |
| **`class DateTimeTZRange`** | `class` · Init: `(lower=None, upper=None, bounds='[)', empty=False)` · Attrs: `isempty`, `lower`, `lower_inc`, `lower_inf`, `upper`, `upper_inc`, `upper_inf`<br>Represents :sql:`tstzrange` values. |
| **`class DictConnection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(self, *args, **kwargs)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>A connection that uses `DictCursor` automatically. |
| **`class DictCursor`** | `class` · Init: `(*args, **kwargs)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(self, procname, vars=None)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>A cursor that keeps a list of column name -> index mappings__. |
| **`class DictCursorBase`** | `class` · Init: `(*args, **kwargs)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(...)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>Base class for all dict-like cursors. |
| **`class DictRow`** | `class` · Init: `(cursor)` · Attrs: `append`, `clear`, `copy`, `count`, `extend`, `get`, `index`, `insert`, `items`, `keys` · Methods: `append(self, object, /)`, `clear(self, /)`, `copy(self)`, `count(self, value, /)`, `extend(self, iterable, /)`, `get(self, x, default=None)`<br>A row object that allow by-column-name access to data. |
| **`class HstoreAdapter`** | `class` · Init: `(wrapped)` · Attrs: `get_oids`, `getquoted`, `parse`, `parse_unicode`, `prepare` · Methods: `get_oids(conn_or_curs)`, `getquoted(self)`, `parse(s, cur, _bsdec=re.compile('\\\\(.)'))`, `parse_unicode(s, cur)`, `prepare(self, conn)`<br>Adapt a Python dict to the hstore syntax. |
| **`class Inet`** | `class` · Init: `(addr)` · Attrs: `getquoted`, `prepare` · Methods: `getquoted(self)`, `prepare(self, conn)`<br>Wrap a string to allow for correct SQL-quoting of inet values. |
| **`class Json`** | `class` · Init: `(adapted, dumps=None)` · Attrs: `dumps`, `getquoted`, `prepare` · Methods: `dumps(self, obj)`, `getquoted(self)`, `prepare(self, conn)`<br>An `~psycopg2.extensions.ISQLQuote` wrapper to adapt a Python object to :sql:`json` data type. |
| **`class LoggingConnection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(self, *args, **kwargs)`, `fileno(self, /)`, `filter(self, msg, curs)`<br>A connection that logs all queries to a file or logger__ object. |
| **`class LoggingCursor`** | `class` · Init: `(...)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(self, procname, vars=None)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>A cursor that logs queries using its connection logging facilities. |
| **`class LogicalReplicationConnection`** | `class` · Init: `(*args, **kwargs)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(...)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>A replication connection. |
| **`class MinTimeLoggingConnection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(self, *args, **kwargs)`, `fileno(self, /)`, `filter(self, msg, curs)`<br>A connection that logs queries based on execution time. |
| **`class MinTimeLoggingCursor`** | `class` · Init: `(...)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(self, procname, vars=None)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>The cursor sub-class companion to `MinTimeLoggingConnection`. |
| **`class NamedTupleConnection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(self, *args, **kwargs)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>A connection that uses `NamedTupleCursor` automatically. |
| **`class NamedTupleCursor`** | `class` · Init: `(...)` · Attrs: `MAX_CACHE`, `Record`, `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert` · Methods: `callproc(self, procname, vars=None)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>A cursor that generates results as `~collections.namedtuple`. |
| **`class NumericRange`** | `class` · Init: `(lower=None, upper=None, bounds='[)', empty=False)` · Attrs: `isempty`, `lower`, `lower_inc`, `lower_inf`, `upper`, `upper_inc`, `upper_inf`<br>A `Range` suitable to pass Python numeric types to a PostgreSQL range. |
| **`class PhysicalReplicationConnection`** | `class` · Init: `(*args, **kwargs)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(...)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>A replication connection. |
| `REPLICATION_LOGICAL` | `variable` · Type: `int` · Value: `87654321` |
| `REPLICATION_PHYSICAL` | `variable` · Type: `int` · Value: `12345678` |
| **`class Range`** | `class` · Init: `(lower=None, upper=None, bounds='[)', empty=False)` · Attrs: `isempty`, `lower`, `lower_inc`, `lower_inf`, `upper`, `upper_inc`, `upper_inf`<br>Python representation for a PostgreSQL \|range\|_ type. |
| **`class RangeAdapter`** | `class` · Init: `(adapted)` · Attrs: `getquoted`, `name`, `prepare` · Methods: `getquoted(self)`, `prepare(self, conn)`<br>`ISQLQuote` adapter for `Range` subclasses. |
| **`class RangeCaster`** | `class` · Init: `(pgrange, pyrange, oid, subtype_oid, array_oid=None)` · Attrs: `parse` · Methods: `parse(self, s, cur=None)`<br>Helper class to convert between `Range` and PostgreSQL range types. |
| **`class RealDictConnection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(self, *args, **kwargs)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>A connection that uses `RealDictCursor` automatically. |
| **`class RealDictCursor`** | `class` · Init: `(*args, **kwargs)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(self, procname, vars=None)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>A cursor that uses a real dict as the base type for rows. |
| **`class RealDictRow`** | `class` · Init: `(*args, **kwargs)` · Attrs: `clear`, `copy`, `fromkeys`, `get`, `items`, `keys`, `move_to_end`, `pop`, `popitem`, `setdefault` · Methods: `clear(self, /)`, `copy(self, /)`, `fromkeys(iterable, value=None)`, `get(self, key, default=None, /)`, `items(self, /)`, `keys(self, /)`<br>A `!dict` subclass representing a data record. |
| **`class ReplicationCursor`** | `class` · Init: `(...)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `consume_stream`, `copy_expert`, `copy_from` · Methods: `callproc(...)`, `cast(...)`, `close(self, /)`, `consume_stream(...)`, `copy_expert(...)`, `copy_from(...)`<br>A cursor used for communication on replication connections. |
| **`class ReplicationMessage`** | `class` · Init: `(...)` · Attrs: `cursor`, `data_size`, `data_start`, `payload`, `send_time`, `wal_end`<br>A replication protocol message. |
| **`class StopReplication`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception used to break out of the endless loop in `~ReplicationCursor.consume_stream()`. |
| **`class UUID_adapter`** | `class` · Init: `(uuid)` · Attrs: `getquoted` · Methods: `getquoted(self)`<br>Adapt Python's uuid.UUID__ type to PostgreSQL's uuid__. |
| `execute_batch()` | `function` · Signature: `(cur, sql, argslist, page_size=100)`<br>Execute groups of statements in fewer server roundtrips. |
| `execute_values()` | `function` · Signature: `(cur, sql, argslist, template=None, page_size=100, fetch=False)`<br>Execute a statement using :sql:`VALUES` with a sequence of parameters. |
| `quote_ident()` | `function` · Signature: `(...)`<br>quote_ident(str, conn_or_curs) -> str -- wrapper around PQescapeIdentifier |
| `register_composite()` | `function` · Signature: `(name, conn_or_curs, globally=False, factory=None)`<br>Register a typecaster to convert a composite type into a tuple. |
| `register_default_json()` | `function` · Signature: `(conn_or_curs=None, globally=False, loads=None)`<br>Create and register :sql:`json` typecasters for PostgreSQL 9.2 and following. |
| `register_default_jsonb()` | `function` · Signature: `(conn_or_curs=None, globally=False, loads=None)`<br>Create and register :sql:`jsonb` typecasters for PostgreSQL 9.4 and following. |
| `register_hstore()` | `function` · Signature: `(conn_or_curs, globally=False, unicode=False, oid=None, array_oid=None)`<br>Register adapter and typecaster for `!dict`\-\ \|hstore\| conversions. |
| `register_inet()` | `function` · Signature: `(oid=None, conn_or_curs=None)`<br>Create the INET type and an Inet adapter. |
| `register_ipaddress()` | `function` · Signature: `(conn_or_curs=None)`<br>Register conversion support between `ipaddress` objects and `network types`__. |
| `register_json()` | `function` · Signature: `(conn_or_curs=None, globally=False, loads=None, oid=None, array_oid=None, name='json')`<br>Create and register typecasters converting :sql:`json` type to Python objects. |
| `register_range()` | `function` · Signature: `(pgrange, pyrange, conn_or_curs, globally=False)`<br>Create and register an adapter and the typecasters to convert between a PostgreSQL \|range\|_ type and a PostgreSQL `Range` subclass. |
| `register_uuid()` | `function` · Signature: `(oids=None, conn_or_curs=None)`<br>Create the UUID type and an uuid.UUID adapter. |
| `wait_select()` | `function` · Signature: `(conn)`<br>Wait until a connection or cursor has data available. |

### `psycopg2.extensions`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class AsIs`** | `class` · Init: `(...)` · Attrs: `adapted`, `getquoted` · Methods: `getquoted(self, /)`<br>AsIs(str) -> new AsIs adapter object |
| `BINARYARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `BOOLEAN()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `BOOLEANARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `BYTES()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `BYTESARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class Binary`** | `class` · Init: `(...)` · Attrs: `adapted`, `buffer`, `getquoted`, `prepare` · Methods: `getquoted(self, /)`, `prepare(...)`<br>Binary(buffer) -> new binary object |
| **`class Boolean`** | `class` · Init: `(...)` · Attrs: `adapted`, `getquoted` · Methods: `getquoted(self, /)`<br>Boolean(str) -> new Boolean adapter object |
| **`class Column`** | `class` · Init: `(...)` · Attrs: `display_size`, `internal_size`, `name`, `null_ok`, `precision`, `scale`, `table_column`, `table_oid`, `type_code`<br>Description of a column returned by a query. |
| **`class ConnectionInfo`** | `class` · Init: `(...)` · Attrs: `backend_pid`, `dbname`, `dsn_parameters`, `error_message`, `host`, `needs_password`, `options`, `parameter_status`, `password`, `port` · Methods: `parameter_status(...)`, `ssl_attribute(...)`<br>Details about the native PostgreSQL database connection. |
| `DATE()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `DATEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `DATETIMEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `DECIMAL()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `DECIMALARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `DateFromPy()` | `function` · Signature: `(...)`<br>DateFromPy(datetime.date) -> new wrapper |
| **`class Diagnostics`** | `class` · Init: `(...)` · Attrs: `column_name`, `constraint_name`, `context`, `datatype_name`, `internal_position`, `internal_query`, `message_detail`, `message_hint`, `message_primary`, `schema_name`<br>Details from a database error report. |
| `FLOAT()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `FLOATARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class Float`** | `class` · Init: `(...)` · Attrs: `adapted`, `getquoted` · Methods: `getquoted(self, /)`<br>Float(str) -> new Float adapter object |
| `INTEGER()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `INTEGERARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `INTERVAL()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `INTERVALARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `ISOLATION_LEVEL_AUTOCOMMIT` | `variable` · Type: `int` · Value: `0` |
| `ISOLATION_LEVEL_DEFAULT` | `variable` · Type: `NoneType` · Value: `None` |
| `ISOLATION_LEVEL_READ_COMMITTED` | `variable` · Type: `int` · Value: `1` |
| `ISOLATION_LEVEL_READ_UNCOMMITTED` | `variable` · Type: `int` · Value: `4` |
| `ISOLATION_LEVEL_REPEATABLE_READ` | `variable` · Type: `int` · Value: `2` |
| `ISOLATION_LEVEL_SERIALIZABLE` | `variable` · Type: `int` · Value: `3` |
| **`class ISQLQuote`** | `class` · Init: `(...)` · Attrs: `getbinary`, `getbuffer`, `getquoted` · Methods: `getbinary(self, /)`, `getbuffer(self, /)`, `getquoted(self, /)`<br>Abstract ISQLQuote protocol |
| **`class Int`** | `class` · Init: `(...)` · Attrs: `adapted`, `getquoted` · Methods: `getquoted(self, /)`<br>Int(str) -> new Int adapter object |
| `IntervalFromPy()` | `function` · Signature: `(...)`<br>IntervalFromPy(datetime.timedelta) -> new wrapper |
| `JSON()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `JSONARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `JSONB()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `JSONBARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `LONGINTEGER()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `LONGINTEGERARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class NoneAdapter`** | `class` · Init: `(obj)` · Attrs: `getquoted` · Methods: `getquoted(self, _null=b'NULL')`<br>Adapt None to NULL. |
| **`class Notify`** | `class` · Init: `(...)` · Attrs: `channel`, `payload`, `pid`<br>A notification received from the backend. |
| `POLL_ERROR` | `variable` · Type: `int` · Value: `3` |
| `POLL_OK` | `variable` · Type: `int` · Value: `0` |
| `POLL_READ` | `variable` · Type: `int` · Value: `1` |
| `POLL_WRITE` | `variable` · Type: `int` · Value: `2` |
| `PYDATE()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYDATEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYDATETIME()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYDATETIMEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYDATETIMETZ()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYDATETIMETZARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYINTERVAL()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYINTERVALARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYTIME()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `PYTIMEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class QueryCanceledError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error related to SQL query cancellation. |
| **`class QuotedString`** | `class` · Init: `(...)` · Attrs: `adapted`, `buffer`, `encoding`, `getquoted`, `prepare` · Methods: `getquoted(self, /)`, `prepare(...)`<br>QuotedString(str) -> new quoted object |
| `ROWIDARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class SQL_IN`** | `class` · Init: `(seq)` · Attrs: `getquoted`, `prepare` · Methods: `getquoted(self)`, `prepare(self, conn)`<br>Adapt any iterable to an SQL quotable object. |
| `STATUS_ASYNC` | `variable` · Type: `int` · Value: `4` |
| `STATUS_BEGIN` | `variable` · Type: `int` · Value: `2` |
| `STATUS_IN_TRANSACTION` | `variable` · Type: `int` · Value: `2` |
| `STATUS_PREPARED` | `variable` · Type: `int` · Value: `5` |
| `STATUS_READY` | `variable` · Type: `int` · Value: `1` |
| `STATUS_SETUP` | `variable` · Type: `int` · Value: `0` |
| `STATUS_SYNC` | `variable` · Type: `int` · Value: `3` |
| `STRINGARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `TIME()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `TIMEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `TRANSACTION_STATUS_ACTIVE` | `variable` · Type: `int` · Value: `1` |
| `TRANSACTION_STATUS_IDLE` | `variable` · Type: `int` · Value: `0` |
| `TRANSACTION_STATUS_INERROR` | `variable` · Type: `int` · Value: `3` |
| `TRANSACTION_STATUS_INTRANS` | `variable` · Type: `int` · Value: `2` |
| `TRANSACTION_STATUS_UNKNOWN` | `variable` · Type: `int` · Value: `4` |
| `TimeFromPy()` | `function` · Signature: `(...)`<br>TimeFromPy(datetime.time) -> new wrapper |
| `TimestampFromPy()` | `function` · Signature: `(...)`<br>TimestampFromPy(datetime.datetime) -> new wrapper |
| **`class TransactionRollbackError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `cursor`, `diag`, `pgcode`, `pgerror`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Error causing transaction rollback (deadlocks, serialization failures, etc). |
| `UNICODE()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| `UNICODEARRAY()` | `function` · Signature: `(*args, **kwargs)`<br>psycopg type-casting object |
| **`class Xid`** | `class` · Init: `(...)` · Attrs: `bqual`, `database`, `format_id`, `from_string`, `gtrid`, `owner`, `prepared` · Methods: `from_string(...)`<br>A transaction identifier used for two-phase commit. |
| `adapt()` | `function` · Signature: `(...)`<br>adapt(obj, protocol, alternate) -> object -- adapt obj to given protocol |
| `adapters` | `variable` · Type: `dict` · Value: `{(<class 'float'>, <class 'psycopg2.extensions.ISQLQuote'...` |
| `binary_types` | `variable` · Type: `dict` · Value: `{}` |
| **`class connection`** | `class` · Init: `(...)` · Attrs: `DataError`, `DatabaseError`, `Error`, `IntegrityError`, `InterfaceError`, `InternalError`, `NotSupportedError`, `OperationalError`, `ProgrammingError`, `Warning` · Methods: `cancel(self, /)`, `close(self, /)`, `commit(self, /)`, `cursor(...)`, `fileno(self, /)`, `get_backend_pid(self, /)`<br>connection(dsn, ...) -> new connection object |
| **`class cursor`** | `class` · Init: `(...)` · Attrs: `arraysize`, `binary_types`, `callproc`, `cast`, `close`, `closed`, `connection`, `copy_expert`, `copy_from`, `copy_to` · Methods: `callproc(...)`, `cast(...)`, `close(self, /)`, `copy_expert(...)`, `copy_from(...)`, `copy_to(...)`<br>A database cursor. |
| `encodings` | `variable` · Type: `dict` · Value: `{'ABC': 'cp1258', 'ALT': 'cp866', 'BIG5': 'big5', 'EUC_CN...` |
| `encrypt_password()` | `function` · Signature: `(...)`<br>encrypt_password(password, user, [scope], [algorithm]) -- Prepares the encrypted form of a PostgreSQL password. |
| `get_wait_callback()` | `function` · Signature: `()`<br>Return the currently registered wait callback. |
| `libpq_version()` | `function` · Signature: `()`<br>Query actual libpq version loaded. |
| **`class lobject`** | `class` · Init: `(...)` · Attrs: `close`, `closed`, `export`, `mode`, `oid`, `read`, `seek`, `tell`, `truncate`, `unlink` · Methods: `close(self, /)`, `export(...)`, `read(...)`, `seek(...)`, `tell(self, /)`, `truncate(...)`<br>A database large object. |
| `make_dsn()` | `function` · Signature: `(dsn=None, **kwargs)`<br>Convert a set of keywords into a connection strings. |
| `new_array_type()` | `function` · Signature: `(...)`<br>new_array_type(oids, name, baseobj) -> new type object |
| `new_type()` | `function` · Signature: `(...)`<br>new_type(oids, name, castobj) -> new type object |
| `parse_dsn()` | `function` · Signature: `(...)`<br>parse_dsn(dsn) -> dict -- parse a connection string into parameters |
| `quote_ident()` | `function` · Signature: `(...)`<br>quote_ident(str, conn_or_curs) -> str -- wrapper around PQescapeIdentifier |
| `register_adapter()` | `function` · Signature: `(typ, callable)`<br>Register 'callable' as an ISQLQuote adapter for type 'typ'. |
| `register_type()` | `function` · Signature: `(...)`<br>register_type(obj, conn_or_curs) -> None -- register obj with psycopg type system |
| `set_wait_callback()` | `function` · Signature: `(object, /)`<br>Register a callback function to block waiting for data. |
| `string_types` | `variable` · Type: `dict` · Value: `{20: <psycopg2._psycopg.type 'LONGINTEGER' at 0x000001A48...` |
