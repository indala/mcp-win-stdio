# `python-docx` (>=1.1.0)

> Word `.docx` document creation, layout/margins, typography, images, tables, and XML namespace inspection.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=1.1.0` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-word/pyproject.toml` |
| **Repo Imports (5)** | `docx (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)`; `from docx.enum.section import WD_ORIENT (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)`; `from docx.enum.text import WD_ALIGN_PARAGRAPH (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)`; `from docx.oxml.ns import nsmap (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)`; `from docx.shared import Inches, Pt, RGBColor (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `docx.Document` | `function` · Params: `(docx: 'str \| IO[bytes] \| None' = None) -> 'DocumentObject'`<br>Return a \|Document\| object loaded from `docx`, where `docx` can be either a path to a ``.docx`` file (a string) or a file-like object.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.section.WD_ORIENT` | `class` · Init: `(*values)` · Key attrs: `LANDSCAPE`, `PORTRAIT`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`<br>Alias: **WD_ORIENT**<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.section.WD_ORIENT.LANDSCAPE` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.section.WD_ORIENT.PORTRAIT` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.text.WD_ALIGN_PARAGRAPH` | `class` · Init: `(*values)` · Key attrs: `CENTER`, `DISTRIBUTE`, `JUSTIFY`, `JUSTIFY_HI`, `JUSTIFY_LOW`, `JUSTIFY_MED`, `LEFT`, `RIGHT`<br>Alias: **WD_ALIGN_PARAGRAPH**<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.text.WD_ALIGN_PARAGRAPH.JUSTIFY` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.oxml.ns.nsmap` | `variable` (`dict`) · Value: `{'a': 'http://schemas.openxmlformats.org/drawingml/2006/m...`<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.shared.Inches` | `class` · Init: `(inches: 'float')` · Key attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`<br>Convenience constructor for length in inches, e.g. ``width = Inches(0.5)``.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.shared.Pt` | `class` · Init: `(points: 'float')` · Key attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`<br>Convenience value class for specifying a length in points.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `docx.shared.RGBColor` | `class` · Init: `(r: 'int', g: 'int', b: 'int')` · Key attrs: `count`, `from_string`, `index`<br>Immutable value object defining a particular RGB color.<br>**Used in:** `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |

## Public Functions, Classes & Variables

### `docx`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `Document()` | `function` · Signature: `(docx: 'str \| IO[bytes] \| None' = None) -> 'DocumentObject'`<br>Return a \|Document\| object loaded from `docx`, where `docx` can be either a path to a ``.docx`` file (a string) or a file-like object. |

### `docx.shared`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class Cm`** | `class` · Init: `(cm: 'float')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience constructor for length in centimeters, e.g. ``height = Cm(12)``. |
| **`class ElementProxy`** | `class` · Init: `(element: 'BaseOxmlElement', parent: 't.ProvidesXmlPart \| None' = None)` · Attrs: `element`, `part`<br>Base class for lxml element proxy classes. |
| **`class Emu`** | `class` · Init: `(emu: 'int')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience constructor for length in English Metric Units, e.g. ``width = Emu(457200)``. |
| **`class Inches`** | `class` · Init: `(inches: 'float')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience constructor for length in inches, e.g. ``width = Inches(0.5)``. |
| **`class Length`** | `class` · Init: `(emu: 'int')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Base class for length constructor classes Inches, Cm, Mm, Px, and Emu. |
| **`class Mm`** | `class` · Init: `(mm: 'float')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience constructor for length in millimeters, e.g. ``width = Mm(240.5)``. |
| **`class Parented`** | `class` · Init: `(parent: 't.ProvidesXmlPart')` · Attrs: `part`<br>Provides common services for document elements that occur below a part but may occasionally require an ancestor object to provide a service, such as add or drop a relationship. |
| **`class Pt`** | `class` · Init: `(points: 'float')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience value class for specifying a length in points. |
| **`class RGBColor`** | `class` · Init: `(r: 'int', g: 'int', b: 'int')` · Attrs: `count`, `from_string`, `index` · Methods: `count(self, value, /)`, `from_string(rgb_hex_str: 'str') -> 'RGBColor'`, `index(self, value, start=0, stop=9223372036854775807, /)`<br>Immutable value object defining a particular RGB color. |
| **`class StoryChild`** | `class` · Init: `(parent: 't.ProvidesStoryPart')` · Attrs: `part`<br>A document element within a story part. |
| `T` | `variable` · Type: `TypeVar` · Value: `~T` |
| `TYPE_CHECKING` | `variable` · Type: `bool` · Value: `False` |
| **`class TextAccumulator`** | `class` · Init: `(separator: 'str' = '')` · Attrs: `pop`, `push` · Methods: `pop(self) -> 'Iterator[str]'`, `push(self, text: 'str') -> 'None'`<br>Accepts `str` fragments and joins them together, in order, on `.pop(). |
| **`class Twips`** | `class` · Init: `(twips: 'float')` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `cm`, `conjugate`, `denominator`, `emu`, `from_bytes`, `imag`, `inches` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Convenience constructor for length in twips, e.g. ``width = Twips(42)``. |
| `annotations` | `variable` · Type: `_Feature` · Value: `_Feature((3, 7, 0, 'beta', 1), None, 16777216)` |
| **`class lazyproperty`** | `class` · Init: `(fget: 'Callable[..., T]') -> 'None'`<br>Decorator like @property, but evaluated only on first access. |
| `write_only_property()` | `function` · Signature: `(f: 'Callable[[Any, Any], None]')`<br>@write_only_property decorator. |

### `docx.enum.section`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class BaseXmlEnum`** | `class` · Init: `(new_class_name, /, names, *, module=None, qualname=None, type=None, start=1, boundary=None)` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag`, `is_integer`, `numerator`, `real` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Base class for Enums that also map XML attr values. |
| **`class WD_HEADER_FOOTER`** | `class` · Init: `(*values)` · Attrs: `EVEN_PAGE`, `FIRST_PAGE`, `PRIMARY`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_HEADER_FOOTER** |
| **`class WD_HEADER_FOOTER_INDEX`** | `class` · Init: `(*values)` · Attrs: `EVEN_PAGE`, `FIRST_PAGE`, `PRIMARY`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_HEADER_FOOTER** |
| **`class WD_ORIENT`** | `class` · Init: `(*values)` · Attrs: `LANDSCAPE`, `PORTRAIT`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag`, `is_integer` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_ORIENT** |
| **`class WD_ORIENTATION`** | `class` · Init: `(*values)` · Attrs: `LANDSCAPE`, `PORTRAIT`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag`, `is_integer` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_ORIENT** |
| **`class WD_SECTION`** | `class` · Init: `(*values)` · Attrs: `CONTINUOUS`, `EVEN_PAGE`, `NEW_COLUMN`, `NEW_PAGE`, `ODD_PAGE`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_SECTION** |
| **`class WD_SECTION_START`** | `class` · Init: `(*values)` · Attrs: `CONTINUOUS`, `EVEN_PAGE`, `NEW_COLUMN`, `NEW_PAGE`, `ODD_PAGE`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_SECTION** |

### `docx.enum.text`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class BaseXmlEnum`** | `class` · Init: `(new_class_name, /, names, *, module=None, qualname=None, type=None, start=1, boundary=None)` · Attrs: `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `denominator`, `from_bytes`, `imag`, `is_integer`, `numerator`, `real` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Base class for Enums that also map XML attr values. |
| **`class WD_ALIGN_PARAGRAPH`** | `class` · Init: `(*values)` · Attrs: `CENTER`, `DISTRIBUTE`, `JUSTIFY`, `JUSTIFY_HI`, `JUSTIFY_LOW`, `JUSTIFY_MED`, `LEFT`, `RIGHT`, `THAI_JUSTIFY`, `as_integer_ratio` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_ALIGN_PARAGRAPH** |
| **`class WD_BREAK`** | `class` · Init: `(*values)` · Attrs: `COLUMN`, `LINE`, `LINE_CLEAR_ALL`, `LINE_CLEAR_LEFT`, `LINE_CLEAR_RIGHT`, `PAGE`, `SECTION_CONTINUOUS`, `SECTION_EVEN_PAGE`, `SECTION_NEXT_PAGE`, `SECTION_ODD_PAGE`<br>Corresponds to WdBreakType enumeration. |
| **`class WD_BREAK_TYPE`** | `class` · Init: `(*values)` · Attrs: `COLUMN`, `LINE`, `LINE_CLEAR_ALL`, `LINE_CLEAR_LEFT`, `LINE_CLEAR_RIGHT`, `PAGE`, `SECTION_CONTINUOUS`, `SECTION_EVEN_PAGE`, `SECTION_NEXT_PAGE`, `SECTION_ODD_PAGE`<br>Corresponds to WdBreakType enumeration. |
| **`class WD_COLOR`** | `class` · Init: `(*values)` · Attrs: `AUTO`, `BLACK`, `BLUE`, `BRIGHT_GREEN`, `DARK_BLUE`, `DARK_RED`, `DARK_YELLOW`, `GRAY_25`, `GRAY_50`, `GREEN` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`<br>Specifies a standard preset color to apply. |
| **`class WD_COLOR_INDEX`** | `class` · Init: `(*values)` · Attrs: `AUTO`, `BLACK`, `BLUE`, `BRIGHT_GREEN`, `DARK_BLUE`, `DARK_RED`, `DARK_YELLOW`, `GRAY_25`, `GRAY_50`, `GREEN` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`<br>Specifies a standard preset color to apply. |
| **`class WD_LINE_SPACING`** | `class` · Init: `(*values)` · Attrs: `AT_LEAST`, `DOUBLE`, `EXACTLY`, `MULTIPLE`, `ONE_POINT_FIVE`, `SINGLE`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Specifies a line spacing format to be applied to a paragraph. |
| **`class WD_PARAGRAPH_ALIGNMENT`** | `class` · Init: `(*values)` · Attrs: `CENTER`, `DISTRIBUTE`, `JUSTIFY`, `JUSTIFY_HI`, `JUSTIFY_LOW`, `JUSTIFY_MED`, `LEFT`, `RIGHT`, `THAI_JUSTIFY`, `as_integer_ratio` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Alias: **WD_ALIGN_PARAGRAPH** |
| **`class WD_TAB_ALIGNMENT`** | `class` · Init: `(*values)` · Attrs: `BAR`, `CENTER`, `CLEAR`, `DECIMAL`, `END`, `LEFT`, `LIST`, `NUM`, `RIGHT`, `START` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Specifies the tab stop alignment to apply. |
| **`class WD_TAB_LEADER`** | `class` · Init: `(*values)` · Attrs: `DASHES`, `DOTS`, `HEAVY`, `LINES`, `MIDDLE_DOT`, `SPACES`, `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`, `is_integer(self, /)`<br>Specifies the character to use as the leader with formatted tabs. |
| **`class WD_UNDERLINE`** | `class` · Init: `(*values)` · Attrs: `DASH`, `DASH_HEAVY`, `DASH_LONG`, `DASH_LONG_HEAVY`, `DOTTED`, `DOTTED_HEAVY`, `DOT_DASH`, `DOT_DASH_HEAVY`, `DOT_DOT_DASH`, `DOT_DOT_DASH_HEAVY` · Methods: `as_integer_ratio(self, /)`, `bit_count(self, /)`, `bit_length(self, /)`, `conjugate(self, /)`, `from_bytes(bytes, byteorder='big', *, signed=False)`<br>Specifies the style of underline applied to a run of characters. |
| `annotations` | `variable` · Type: `_Feature` · Value: `_Feature((3, 7, 0, 'beta', 1), None, 16777216)` |

### `docx.oxml.ns`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class NamespacePrefixedTag`** | `class` · Init: `(nstag: 'str')` · Attrs: `capitalize`, `casefold`, `center`, `clark_name`, `count`, `encode`, `endswith`, `expandtabs`, `find`, `format` · Methods: `capitalize(self, /)`, `casefold(self, /)`, `center(self, width, fillchar=' ', /)`, `count(...)`, `encode(self, /, encoding='utf-8', errors='strict')`, `endswith(...)`<br>Value object that knows the semantics of an XML tag having a namespace prefix. |
| `annotations` | `variable` · Type: `_Feature` · Value: `_Feature((3, 7, 0, 'beta', 1), None, 16777216)` |
| `nsdecls()` | `function` · Signature: `(*prefixes: 'str') -> 'str'`<br>Namespace declaration including each namespace-prefix in `prefixes`. |
| `nsmap` | `variable` · Type: `dict` · Value: `{'a': 'http://schemas.openxmlformats.org/drawingml/2006/m...` |
| `nspfxmap()` | `function` · Signature: `(*nspfxs: 'str') -> 'Dict[str, str]'`<br>Subset namespace-prefix mappings specified by *nspfxs*. |
| `pfxmap` | `variable` · Type: `dict` · Value: `{'http://schemas.openxmlformats.org/drawingml/2006/main':...` |
| `qn()` | `function` · Signature: `(tag: 'str') -> 'str'`<br>Stands for "qualified name". |
