# `pywin32` (>=306 (Windows only))

> Windows COM automation (`Excel.Application`, `Word.Application`), apartment initialization (`pythoncom`), and Windows Credential Manager (`win32cred`).

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=306 (Windows only)` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-excel/pyproject.toml`, `packages/mcp-win-stdio-word/pyproject.toml` |
| **Repo Imports (8)** | `win32com.client (packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/cli.py)`; `win32com.client (packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py)`; `win32com.client (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/cli.py)`; `win32com.client (packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py)`; `win32com.client (src/mcp_win_stdio/cli.py)` *(+3 more)* |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `pythoncom.CoInitialize` | `function` · Params: `(...)`<br>Function used by `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py`, `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |
| `pythoncom.CoUninitialize` | `function` · Params: `(...)`<br>Function used by `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-excel/src/mcp_win_stdio/excel/server.py`, `packages/mcp-win-stdio-word/src/mcp_win_stdio/word/server.py` |

## Public Functions, Classes & Variables

### `win32com.client`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class CDispatch`** | `class` · Init: `(IDispatch, olerepr, userName=None, lazydata=None)`<br>The dynamic class used as a last resort. The purpose of this overriding of dynamic.CDispatch is to perpetuate the policy of using the makepy generated wrapper Python class instead of dynamic.CDispatch if/when possible. |
| `CastTo()` | `function` · Signature: `(ob, target, typelib=None)`<br>'Cast' a COM object to another interface |
| **`class CoClassBaseClass`** | `class` · Init: `(oobj=None)`<br>Public class. |
| **`class Constants`** | `class` · Init: `()`<br>A container for generated COM constants. |
| `Dispatch()` | `function` · Signature: `(dispatch, userName=None, resultCLSID=None, typeinfo=None, clsctx=21)`<br>Creates a Dispatch based COM object. |
| **`class DispatchBaseClass`** | `class` · Init: `(oobj=None)`<br>Public class. |
| `DispatchEx()` | `function` · Signature: `(clsid, machine=None, userName=None, resultCLSID=None, typeinfo=None, clsctx=None)`<br>Creates a Dispatch based COM object on a specific machine. |
| `DispatchWithEvents()` | `function` · Signature: `(clsid, user_event_class) -> 'EventsProxy'`<br>Create a COM object that can fire events to a user defined class. clsid -- The ProgID or CLSID of the object to create. user_event_class -- A Python class object that responds to the events. |
| **`class EventsProxy`** | `class` · Init: `(ob)`<br>Public class. |
| `GetActiveObject()` | `function` · Signature: `(Class, clsctx=23)`<br>Python friendly version of GetObject's ProgID/CLSID functionality. |
| `GetObject()` | `function` · Signature: `(Pathname=None, Class=None, clsctx=None)`<br>Mimic VB's GetObject() function. |
| `Moniker()` | `function` · Signature: `(Pathname, clsctx=23)`<br>Python friendly version of GetObject's moniker functionality. |
| `Record()` | `function` · Signature: `(name, object)`<br>Creates a new record object, given the name of the record, and an object from the same type library. |
| **`class VARIANT`** | `class` · Init: `(vt, value)` · Attrs: `value`<br>Public class. |
| `WithEvents()` | `function` · Signature: `(disp, user_event_class)`<br>Similar to DispatchWithEvents - except that the returned object is *not* also usable as the original Dispatch object - that is the returned object is not dispatchable. |
| `annotations` | `variable` · Type: `_Feature` · Value: `_Feature((3, 7, 0, 'beta', 1), None, 16777216)` |
| `constants` | `variable` · Type: `Constants` · Value: `<win32com.client.Constants object at 0x000001A489318830>` |
| `getevents()` | `function` · Signature: `(clsid)`<br>Determine the default outgoing interface for a class, given either a clsid or progid. It returns a class - you can conveniently derive your own handler from this class and implement the appropriate methods. |
| `register_record_class()` | `function` · Signature: `(cls)`<br>Register a subclass of com_record to enable creation of the represented record objects. |

### `pythoncom`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `ACTIVEOBJECT_STRONG` | `variable` · Type: `int` · Value: `0` |
| `ACTIVEOBJECT_WEAK` | `variable` · Type: `int` · Value: `1` |
| `ArgNotFound` | `variable` · Type: `ArgNotFound` · Value: `<ArgNotFound object at 0x000001A4E6D68820>` |
| `CLSCTX_ALL` | `variable` · Type: `int` · Value: `23` |
| `CLSCTX_INPROC` | `variable` · Type: `int` · Value: `3` |
| `CLSCTX_INPROC_HANDLER` | `variable` · Type: `int` · Value: `2` |
| `CLSCTX_INPROC_SERVER` | `variable` · Type: `int` · Value: `1` |
| `CLSCTX_LOCAL_SERVER` | `variable` · Type: `int` · Value: `4` |
| `CLSCTX_REMOTE_SERVER` | `variable` · Type: `int` · Value: `16` |
| `CLSCTX_SERVER` | `variable` · Type: `int` · Value: `21` |
| `CLSID_DCOMAccessControl` | `variable` · Type: `PyIID` · Value: `IID('{0000031D-0000-0000-C000-000000000046}')` |
| `CLSID_StdComponentCategoriesMgr` | `variable` · Type: `PyIID` · Value: `IID('{0002E005-0000-0000-C000-000000000046}')` |
| `CLSID_StdGlobalInterfaceTable` | `variable` · Type: `PyIID` · Value: `IID('{00000323-0000-0000-C000-000000000046}')` |
| `COINIT_APARTMENTTHREADED` | `variable` · Type: `int` · Value: `2` |
| `COINIT_DISABLE_OLE1DDE` | `variable` · Type: `int` · Value: `4` |
| `COINIT_MULTITHREADED` | `variable` · Type: `int` · Value: `0` |
| `COINIT_SPEED_OVER_MEMORY` | `variable` · Type: `int` · Value: `8` |
| `COWAIT_ALERTABLE` | `variable` · Type: `int` · Value: `2` |
| `COWAIT_WAITALL` | `variable` · Type: `int` · Value: `1` |
| `CoCreateFreeThreadedMarshaler()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoCreateInstance()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoCreateInstanceEx()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoDisableCallCancellation()` | `function` · Signature: `()`<br>Public function/callable. |
| `CoEnableCallCancellation()` | `function` · Signature: `()`<br>Public function/callable. |
| `CoFreeUnusedLibraries()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoGetCallContext()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoGetCancelObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoGetInterfaceAndReleaseStream()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoGetObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoGetObjectContext()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoInitialize()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoInitializeEx()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoInitializeSecurity()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoMarshalInterThreadInterfaceInStream()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoMarshalInterface()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoRegisterClassObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoReleaseMarshalData()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoResumeClassObjects()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoRevokeClassObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoSetCancelObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoTreatAsClass()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoUninitialize()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoUnmarshalInterface()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CoWaitForMultipleHandles()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `Connect()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateBindCtx()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateFileMoniker()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateGuid()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateILockBytesOnHGlobal()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateItemMoniker()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreatePointerMoniker()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateStreamOnHGlobal()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateTypeLib()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateTypeLib2()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `CreateURLMonikerEx()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `DATADIR_GET` | `variable` · Type: `int` · Value: `1` |
| `DATADIR_SET` | `variable` · Type: `int` · Value: `2` |
| `DESCKIND_FUNCDESC` | `variable` · Type: `int` · Value: `1` |
| `DESCKIND_VARDESC` | `variable` · Type: `int` · Value: `2` |
| `DISPATCH_METHOD` | `variable` · Type: `int` · Value: `1` |
| `DISPATCH_PROPERTYGET` | `variable` · Type: `int` · Value: `2` |
| `DISPATCH_PROPERTYPUT` | `variable` · Type: `int` · Value: `4` |
| `DISPATCH_PROPERTYPUTREF` | `variable` · Type: `int` · Value: `8` |
| `DISPID_COLLECT` | `variable` · Type: `int` · Value: `-8` |
| `DISPID_CONSTRUCTOR` | `variable` · Type: `int` · Value: `-6` |
| `DISPID_DESTRUCTOR` | `variable` · Type: `int` · Value: `-7` |
| `DISPID_EVALUATE` | `variable` · Type: `int` · Value: `-5` |
| `DISPID_NEWENUM` | `variable` · Type: `int` · Value: `-4` |
| `DISPID_PROPERTYPUT` | `variable` · Type: `int` · Value: `-3` |
| `DISPID_STARTENUM` | `variable` · Type: `int` · Value: `-1` |
| `DISPID_THIS` | `variable` · Type: `int` · Value: `-613` |
| `DISPID_UNKNOWN` | `variable` · Type: `int` · Value: `-1` |
| `DISPID_VALUE` | `variable` · Type: `int` · Value: `0` |
| `DVASPECT_CONTENT` | `variable` · Type: `int` · Value: `1` |
| `DVASPECT_DOCPRINT` | `variable` · Type: `int` · Value: `8` |
| `DVASPECT_ICON` | `variable` · Type: `int` · Value: `4` |
| `DVASPECT_THUMBNAIL` | `variable` · Type: `int` · Value: `2` |
| `DoDragDrop()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `EOAC_ACCESS_CONTROL` | `variable` · Type: `int` · Value: `4` |
| `EOAC_ANY_AUTHORITY` | `variable` · Type: `int` · Value: `128` |
| `EOAC_APPID` | `variable` · Type: `int` · Value: `8` |
| `EOAC_AUTO_IMPERSONATE` | `variable` · Type: `int` · Value: `1024` |
| `EOAC_DEFAULT` | `variable` · Type: `int` · Value: `2048` |
| `EOAC_DISABLE_AAA` | `variable` · Type: `int` · Value: `4096` |
| `EOAC_DYNAMIC` | `variable` · Type: `int` · Value: `16` |
| `EOAC_DYNAMIC_CLOAKING` | `variable` · Type: `int` · Value: `64` |
| `EOAC_MAKE_FULLSIC` | `variable` · Type: `int` · Value: `256` |
| `EOAC_MUTUAL_AUTH` | `variable` · Type: `int` · Value: `1` |
| `EOAC_NONE` | `variable` · Type: `int` · Value: `0` |
| `EOAC_NO_CUSTOM_MARSHAL` | `variable` · Type: `int` · Value: `8192` |
| `EOAC_REQUIRE_FULLSIC` | `variable` · Type: `int` · Value: `512` |
| `EOAC_SECURE_REFS` | `variable` · Type: `int` · Value: `2` |
| `EOAC_STATIC_CLOAKING` | `variable` · Type: `int` · Value: `32` |
| `EXTCONN_CALLABLE` | `variable` · Type: `int` · Value: `4` |
| `EXTCONN_STRONG` | `variable` · Type: `int` · Value: `1` |
| `EXTCONN_WEAK` | `variable` · Type: `int` · Value: `2` |
| `Empty` | `variable` · Type: `PyOleEmpty` · Value: `<PyOleEmpty object at 0x000001A4E6D687A0>` |
| `EnableQuitMessage()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `FMTID_DocSummaryInformation` | `variable` · Type: `PyIID` · Value: `IID('{D5CDD502-2E9C-101B-9397-08002B2CF9AE}')` |
| `FMTID_SummaryInformation` | `variable` · Type: `PyIID` · Value: `IID('{F29F85E0-4FF9-1068-AB91-08002B27B3D9}')` |
| `FMTID_UserDefinedProperties` | `variable` · Type: `PyIID` · Value: `IID('{D5CDD505-2E9C-101B-9397-08002B2CF9AE}')` |
| `FUNCDESC()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `FUNCFLAG_FBINDABLE` | `variable` · Type: `int` · Value: `4` |
| `FUNCFLAG_FDEFAULTBIND` | `variable` · Type: `int` · Value: `32` |
| `FUNCFLAG_FDISPLAYBIND` | `variable` · Type: `int` · Value: `16` |
| `FUNCFLAG_FHIDDEN` | `variable` · Type: `int` · Value: `64` |
| `FUNCFLAG_FREQUESTEDIT` | `variable` · Type: `int` · Value: `8` |
| `FUNCFLAG_FRESTRICTED` | `variable` · Type: `int` · Value: `1` |
| `FUNCFLAG_FSOURCE` | `variable` · Type: `int` · Value: `2` |
| `FUNCFLAG_FUSESGETLASTERROR` | `variable` · Type: `int` · Value: `128` |
| `FUNC_DISPATCH` | `variable` · Type: `int` · Value: `4` |
| `FUNC_NONVIRTUAL` | `variable` · Type: `int` · Value: `2` |
| `FUNC_PUREVIRTUAL` | `variable` · Type: `int` · Value: `1` |
| `FUNC_STATIC` | `variable` · Type: `int` · Value: `3` |
| `FUNC_VIRTUAL` | `variable` · Type: `int` · Value: `0` |
| `FmtIdToPropStgName()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `GetActiveObject()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `GetClassFile()` | `function` · Signature: `(...)`<br>Public function/callable. |
| `GetFacilityString()` | `function` · Signature: `(...)`<br>Public function/callable. |

### `win32cred`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `CREDUI_FLAGS_ALWAYS_SHOW_UI` | `variable` · Type: `int` · Value: `128` |
| `CREDUI_FLAGS_COMPLETE_USERNAME` | `variable` · Type: `int` · Value: `2048` |
| `CREDUI_FLAGS_DO_NOT_PERSIST` | `variable` · Type: `int` · Value: `2` |
| `CREDUI_FLAGS_EXCLUDE_CERTIFICATES` | `variable` · Type: `int` · Value: `8` |
| `CREDUI_FLAGS_EXPECT_CONFIRMATION` | `variable` · Type: `int` · Value: `131072` |
| `CREDUI_FLAGS_GENERIC_CREDENTIALS` | `variable` · Type: `int` · Value: `262144` |
| `CREDUI_FLAGS_INCORRECT_PASSWORD` | `variable` · Type: `int` · Value: `1` |
| `CREDUI_FLAGS_KEEP_USERNAME` | `variable` · Type: `int` · Value: `1048576` |
| `CREDUI_FLAGS_PASSWORD_ONLY_OK` | `variable` · Type: `int` · Value: `512` |
| `CREDUI_FLAGS_PERSIST` | `variable` · Type: `int` · Value: `4096` |
| `CREDUI_FLAGS_PROMPT_VALID` | `variable` · Type: `int` · Value: `1990623` |
| `CREDUI_FLAGS_REQUEST_ADMINISTRATOR` | `variable` · Type: `int` · Value: `4` |
| `CREDUI_FLAGS_REQUIRE_CERTIFICATE` | `variable` · Type: `int` · Value: `16` |
| `CREDUI_FLAGS_REQUIRE_SMARTCARD` | `variable` · Type: `int` · Value: `256` |
| `CREDUI_FLAGS_SERVER_CREDENTIAL` | `variable` · Type: `int` · Value: `16384` |
| `CREDUI_FLAGS_SHOW_SAVE_CHECK_BOX` | `variable` · Type: `int` · Value: `64` |
| `CREDUI_FLAGS_USERNAME_TARGET_CREDENTIALS` | `variable` · Type: `int` · Value: `524288` |
| `CREDUI_FLAGS_VALIDATE_USERNAME` | `variable` · Type: `int` · Value: `1024` |
| `CREDUI_MAX_CAPTION_LENGTH` | `variable` · Type: `int` · Value: `128` |
| `CREDUI_MAX_DOMAIN_TARGET_LENGTH` | `variable` · Type: `int` · Value: `337` |
| `CREDUI_MAX_GENERIC_TARGET_LENGTH` | `variable` · Type: `int` · Value: `32767` |
| `CREDUI_MAX_MESSAGE_LENGTH` | `variable` · Type: `int` · Value: `1024` |
| `CREDUI_MAX_PASSWORD_LENGTH` | `variable` · Type: `int` · Value: `256` |
| `CREDUI_MAX_USERNAME_LENGTH` | `variable` · Type: `int` · Value: `513` |
| `CRED_ALLOW_NAME_RESOLUTION` | `variable` · Type: `int` · Value: `1` |
| `CRED_CACHE_TARGET_INFORMATION` | `variable` · Type: `int` · Value: `1` |
| `CRED_ENUMERATE_ALL_CREDENTIALS` | `variable` · Type: `int` · Value: `1` |
| `CRED_FLAGS_OWF_CRED_BLOB` | `variable` · Type: `int` · Value: `8` |
| `CRED_FLAGS_PASSWORD_FOR_CERT` | `variable` · Type: `int` · Value: `1` |
| `CRED_FLAGS_PROMPT_NOW` | `variable` · Type: `int` · Value: `2` |
| `CRED_FLAGS_USERNAME_TARGET` | `variable` · Type: `int` · Value: `4` |
| `CRED_FLAGS_VALID_FLAGS` | `variable` · Type: `int` · Value: `61695` |
| `CRED_MAX_ATTRIBUTES` | `variable` · Type: `int` · Value: `64` |
| `CRED_MAX_DOMAIN_TARGET_NAME_LENGTH` | `variable` · Type: `int` · Value: `337` |
| `CRED_MAX_GENERIC_TARGET_NAME_LENGTH` | `variable` · Type: `int` · Value: `32767` |
| `CRED_MAX_STRING_LENGTH` | `variable` · Type: `int` · Value: `256` |
| `CRED_MAX_USERNAME_LENGTH` | `variable` · Type: `int` · Value: `513` |
| `CRED_MAX_VALUE_SIZE` | `variable` · Type: `int` · Value: `256` |
| `CRED_PERSIST_ENTERPRISE` | `variable` · Type: `int` · Value: `3` |
| `CRED_PERSIST_LOCAL_MACHINE` | `variable` · Type: `int` · Value: `2` |
| `CRED_PERSIST_NONE` | `variable` · Type: `int` · Value: `0` |
| `CRED_PERSIST_SESSION` | `variable` · Type: `int` · Value: `1` |
| `CRED_PRESERVE_CREDENTIAL_BLOB` | `variable` · Type: `int` · Value: `1` |
| `CRED_TI_CREATE_EXPLICIT_CRED` | `variable` · Type: `int` · Value: `16` |
| `CRED_TI_DOMAIN_FORMAT_UNKNOWN` | `variable` · Type: `int` · Value: `2` |
| `CRED_TI_ONLY_PASSWORD_REQUIRED` | `variable` · Type: `int` · Value: `4` |
| `CRED_TI_SERVER_FORMAT_UNKNOWN` | `variable` · Type: `int` · Value: `1` |
| `CRED_TI_USERNAME_TARGET` | `variable` · Type: `int` · Value: `8` |
| `CRED_TI_VALID_FLAGS` | `variable` · Type: `int` · Value: `61567` |
| `CRED_TI_WORKGROUP_MEMBER` | `variable` · Type: `int` · Value: `32` |
| `CRED_TYPE_DOMAIN_CERTIFICATE` | `variable` · Type: `int` · Value: `3` |
| `CRED_TYPE_DOMAIN_EXTENDED` | `variable` · Type: `int` · Value: `6` |
| `CRED_TYPE_DOMAIN_PASSWORD` | `variable` · Type: `int` · Value: `2` |
| `CRED_TYPE_DOMAIN_VISIBLE_PASSWORD` | `variable` · Type: `int` · Value: `4` |
| `CRED_TYPE_GENERIC` | `variable` · Type: `int` · Value: `1` |
| `CRED_TYPE_GENERIC_CERTIFICATE` | `variable` · Type: `int` · Value: `5` |
| `CRED_TYPE_MAXIMUM` | `variable` · Type: `int` · Value: `7` |
| `CRED_TYPE_MAXIMUM_EX` | `variable` · Type: `int` · Value: `1007` |
| `CertCredential` | `variable` · Type: `int` · Value: `1` |
| `CredDelete()` | `function` · Signature: `(...)`<br>Deletes a stored credential |
| `CredEnumerate()` | `function` · Signature: `(...)`<br>Lists stored credentials for current logon session |
| `CredGetSessionTypes()` | `function` · Signature: `(...)`<br>Returns maximum persistence supported by the current logon session |
| `CredGetTargetInfo()` | `function` · Signature: `(...)`<br>Determines type and location of credential target |
| `CredIsMarshaledCredential()` | `function` · Signature: `(...)`<br>Checks if a string matches the form of a marshaled credential |
| `CredMarshalCredential()` | `function` · Signature: `(...)`<br>Marshals a credential into a unicode string |
| `CredRead()` | `function` · Signature: `(...)`<br>Retrieves a stored credential |
| `CredReadDomainCredentials()` | `function` · Signature: `(...)`<br>Retrieves a user's credentials for a domain or server |
| `CredRename()` | `function` · Signature: `(...)`<br>Changes the target name of stored credentials |
| `CredUICmdLinePromptForCredentials()` | `function` · Signature: `(...)`<br>Prompt for username/passwd from a console app |
| `CredUIConfirmCredentials()` | `function` · Signature: `(...)`<br>Confirms whether credentials entered by user are valid or not |
| `CredUIParseUserName()` | `function` · Signature: `(...)`<br>Parses a full username into domain and username |
| `CredUIPromptForCredentials()` | `function` · Signature: `(...)`<br>Initiates dialog to request user credentials |
| `CredUIReadSSOCredW()` | `function` · Signature: `(...)`<br>Retrieves single sign on username |
| `CredUIStoreSSOCredW()` | `function` · Signature: `(...)`<br>Creates a single sign on credential |
| `CredUnmarshalCredential()` | `function` · Signature: `(...)`<br>Unmarshals credentials formatted using <om win32cred.CredMarshalCredential> |
| `CredWrite()` | `function` · Signature: `(...)`<br>Creates or updates a stored credential |
| `CredWriteDomainCredentials()` | `function` · Signature: `(...)`<br>Creates or updates credential for a domain or server |
| `UsernameTargetCredential` | `variable` · Type: `int` · Value: `2` |
