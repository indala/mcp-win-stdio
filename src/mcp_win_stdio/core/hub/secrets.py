"""
Secret provider abstraction, rotation tracking, and recursive redaction engine.
"""

import hmac
import os
import re
import secrets
from typing import Any, Dict, List, Optional, Protocol, Union

from .models import SecretReference

REDACTED_MARKER = "***REDACTED***"

# Sensitive key patterns in structured dictionaries
SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|api[_-]?key|credential|private[_-]?key|auth|dsn|connection[_-]?string|pwd)",
    re.IGNORECASE,
)

# URI with embedded credentials (e.g. postgresql://user:secret@localhost:5432/db), supporting percent-encoded chars
URI_CREDENTIALS_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<user>(?:%[0-9a-fA-F]{2}|[^:/\s@])+):(?P<pass>(?:%[0-9a-fA-F]{2}|[^@/\s])+)@",
    re.IGNORECASE,
)

# Textual key-value assignments (e.g. password=secret, dsn: "...", connection_string='...')
TEXT_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?P<key>password|token|secret|api[_-]?key|credential|private[_-]?key|dsn|connection[_-]?string|pwd)\s*(?P<sep>[=:])\s*(?P<quote>['\"]?)(?P<val>[^'\"\s,;\r\n]+)(?P=quote)"
)


class SanitizedException(Exception):
    """Safe wrapper representing an exception whose message has been recursively redacted."""

    def __init__(self, original_type_name: str, message: str) -> None:
        self.original_type_name = original_type_name
        self.message = message
        super().__init__(f"[{original_type_name}] {message}")


class SecretProvider(Protocol):
    """Protocol for external secret storage providers."""

    def resolve(self, key: str) -> str:
        """Resolve a secret value by key. Raises KeyError if missing."""
        ...

    def get_version(self, key: str) -> Optional[str]:
        """
        Return an authoritative version or process-salted HMAC version token.
        Never logs or exposes the secret or plaintext hash.
        """
        ...


class EnvSecretProvider:
    """Secret provider backed by environment variables."""

    def __init__(self) -> None:
        # Ephemeral salt unique to this process memory; prevents offline rainbow table attacks
        self._ephemeral_salt = secrets.token_bytes(32)

    def resolve(self, key: str) -> str:
        val = os.environ.get(key)
        if val is None:
            raise KeyError(f"Environment variable '{key}' is not set.")
        return val

    def get_version(self, key: str) -> Optional[str]:
        val = os.environ.get(key)
        if val is None:
            return None
        # Full 64-character SHA-256 HMAC using unguessable in-memory process salt
        return hmac.new(self._ephemeral_salt, val.encode("utf-8"), "sha256").hexdigest()


class WindowsCredentialManagerProvider:
    """Secret provider backed by Windows Credential Manager."""

    def __init__(self) -> None:
        self._ephemeral_salt = secrets.token_bytes(32)

    def resolve(self, key: str) -> str:
        try:
            import win32cred  # type: ignore[import-not-found]

            cred = win32cred.CredRead(key, win32cred.CRED_TYPE_GENERIC, 0)
            blob = cred.get("CredentialBlob", b"")
            return blob.decode("utf-16" if "\x00" in str(blob) else "utf-8")
        except ImportError:
            # Fallback for environments where pywin32 is not compiled or mocking
            env_fallback = os.environ.get(f"WINCRED_{key.replace('/', '_').replace('-', '_')}")
            if env_fallback is not None:
                return env_fallback
            raise RuntimeError("win32cred module not available and no mock environment fallback found.")
        except Exception as exc:
            # Check if it was element not found (error code 1168 on Windows)
            err_msg = str(exc)
            if "1168" in err_msg or "Element not found" in err_msg:
                raise KeyError(f"Credential '{key}' not found in Windows Credential Manager.") from exc
            raise RuntimeError(f"Windows Credential Manager provider error for '{key}': {exc}") from exc

    def get_version(self, key: str) -> Optional[str]:
        try:
            val = self.resolve(key)
            return hmac.new(self._ephemeral_salt, val.encode("utf-8"), "sha256").hexdigest()
        except KeyError:
            return None
        except Exception as exc:
            # Provider failure: re-raise as RuntimeError so rotation check does not silently fail
            raise RuntimeError(f"Secret provider failure during version check for '{key}': {exc}") from exc


class SecretRegistry:
    """Registry coordinating secret providers and generation tracking."""

    def __init__(self) -> None:
        self._providers: Dict[str, SecretProvider] = {
            "env": EnvSecretProvider(),
            "win_cred_manager": WindowsCredentialManagerProvider(),
        }

    def register_provider(self, name: str, provider: SecretProvider) -> None:
        self._providers[name.lower().strip()] = provider

    def resolve_secret(self, ref: SecretReference) -> str:
        prov = self._providers.get(ref.provider.lower())
        if not prov:
            raise ValueError(f"Secret provider '{ref.provider}' is not supported.")
        return prov.resolve(ref.key)

    def get_secret_version(self, ref: SecretReference) -> Optional[str]:
        prov = self._providers.get(ref.provider.lower())
        if not prov:
            return None
        return prov.get_version(ref.key)


# Global secret registry singleton
GLOBAL_SECRET_REGISTRY = SecretRegistry()


def redact_sensitive_data(data: Any) -> Any:
    """
    Recursively redact passwords, tokens, API keys, URIs with credentials,
    and secret fields across nested dictionaries, lists, strings, and exceptions.
    """
    if isinstance(data, dict):
        redacted_dict = {}
        for k, v in data.items():
            key_str = str(k)
            if SENSITIVE_KEY_PATTERN.search(key_str):
                redacted_dict[k] = REDACTED_MARKER
            else:
                redacted_dict[k] = redact_sensitive_data(v)
        return redacted_dict

    if isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(redact_sensitive_data(item) for item in data)

    if isinstance(data, Exception):
        msg = redact_sensitive_text(str(data))
        try:
            return type(data)(msg)
        except Exception:
            # Fall back safely if the original exception constructor requires specific/custom arguments
            return SanitizedException(type(data).__name__, msg)

    if isinstance(data, str):
        return redact_sensitive_text(data)

    return data


def redact_sensitive_text(text: str) -> str:
    """Redact embedded credentials and key assignments from a plain text string."""
    if not text:
        return text

    # 1. Redact URI credentials (including percent-encoded values)
    redacted = URI_CREDENTIALS_PATTERN.sub(r"\g<scheme>\g<user>:" + REDACTED_MARKER + "@", text)

    # 2. Redact key-value assignments
    redacted = TEXT_ASSIGNMENT_PATTERN.sub(r"\g<key>\g<sep>\g<quote>" + REDACTED_MARKER + r"\g<quote>", redacted)

    return redacted
