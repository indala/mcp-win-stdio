"""
Profile Manager: Four-tier resolution precedence, configuration generation tracking,
and explicit missing-profile error enforcement.
"""

import copy
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mcp_win_stdio.core.context import GLOBAL_CONTEXT

from .models import ProfileConfig, ProjectConfig, ServerProfileManifest
from .secrets import GLOBAL_SECRET_REGISTRY, SecretRegistry


class ProfileNotFoundError(KeyError):
    """Raised when an explicitly requested or bound profile does not exist."""

    pass


class ProfileManager:
    """
    Manages named connection profiles for MCP servers, enforcing strict 4-tier
    precedence resolution, configuration generation tracking, and atomic updates.
    Returns defensive snapshots on resolution to prevent caller mutation of internal state.
    """

    def __init__(self, secret_registry: Optional[SecretRegistry] = None) -> None:
        self._lock = threading.RLock()
        self._manifests: Dict[str, ServerProfileManifest] = {}
        self._generations: Dict[str, int] = {}
        self._secret_versions: Dict[Tuple[str, str], Optional[str]] = {}
        self._secrets = secret_registry or GLOBAL_SECRET_REGISTRY

    def register_manifest(self, server: str, manifest: ServerProfileManifest) -> bool:
        """
        Atomically register or replace a server's profile manifest under lock serialization.
        Recomputes secret version baselines inside the lock and removes stale secret keys.
        Returns True and advances generation if configuration changed, False if identical.
        """
        clean_server = server.lower().strip()
        candidate = copy.deepcopy(manifest)

        with self._lock:
            # 1. Compute secret versions under the serialized lock before publication
            candidate_versions: Dict[Tuple[str, str], Optional[str]] = {}
            for pname, profile in candidate.profiles.items():
                for sname, sref in profile.secrets.items():
                    ver = self._secrets.get_secret_version(sref)
                    candidate_versions[(clean_server, f"{pname}:{sname}")] = ver

            existing = self._manifests.get(clean_server)
            if existing is not None and existing.to_dict() == candidate.to_dict():
                # Check if any secret version changed
                versions_changed = any(
                    self._secret_versions.get(k) != v
                    for k, v in candidate_versions.items()
                )
                if not versions_changed:
                    return False

            # 2. Reconcile secret versions: remove stale entries for deleted profiles/secrets
            stale_keys = [k for k in self._secret_versions if k[0] == clean_server]
            for sk in stale_keys:
                del self._secret_versions[sk]
            self._secret_versions.update(candidate_versions)

            # 3. Publish candidate manifest and advance generation atomically
            self._manifests[clean_server] = candidate
            self._generations[clean_server] = self._generations.get(clean_server, 1) + 1
            return True

    def load_manifest_dict(self, server: str, data: Dict[str, Any]) -> bool:
        """
        Atomically validate and load a server profile manifest from a dictionary.
        Returns True if configuration changed (advancing generation), False if identical.
        Raises ValueError if candidate manifest is invalid; previous manifest and generation remain unchanged.
        """
        candidate = ServerProfileManifest.from_dict(data)
        return self.register_manifest(server, candidate)

    def get_generation(self, server: str) -> int:
        """Get the current configuration generation for a server."""
        clean_server = server.lower().strip()
        with self._lock:
            return self._generations.get(clean_server, 1)

    def get_manifest(self, server: str) -> Optional[ServerProfileManifest]:
        """Return a defensive copy of a registered server profile manifest."""
        clean_server = server.lower().strip()
        with self._lock:
            manifest = self._manifests.get(clean_server)
            return copy.deepcopy(manifest) if manifest else None

    def resolve_profile(
        self,
        server: str,
        request_override: Optional[str] = None,
        session_id: Optional[str] = None,
        project_config: Optional[ProjectConfig] = None,
    ) -> Tuple[ProfileConfig, int]:
        """
        Resolve the effective profile using the strict 4-tier precedence ladder:
          Tier 1: Request argument (explicit override)
          Tier 2: Client session context stack (trusted session ID)
          Tier 3: Project declarative binding (.mws/config.yaml)
          Tier 4: Server default profile (manifest.default_profile)

        Returns a defensive copy of the resolved ProfileConfig and current configuration generation.
        """
        clean_server = server.lower().strip()

        with self._lock:
            manifest = self._manifests.get(clean_server)
            if not manifest:
                raise ProfileNotFoundError(f"No profile manifest registered for server '{server}'.")

            chosen_name: Optional[str] = None
            source_tier: Optional[str] = None

            # Tier 1: Explicit Request Override
            if request_override is not None:
                cleaned_override = request_override.strip()
                if not cleaned_override:
                    raise ProfileNotFoundError("Empty or whitespace profile override specified.")
                chosen_name = cleaned_override
                source_tier = "request override"

            # Tier 2: Client Session Context
            if not chosen_name and session_id:
                session = GLOBAL_CONTEXT.get_session(session_id)
                session_val = session.get(f"{clean_server}_profile")
                if not session_val and clean_server in ("db", "excel-db"):
                    # Explicit contract: excel-db shares active db_connection context with db
                    session_val = session.get("db_connection")
                if session_val:
                    chosen_name = str(session_val).strip()
                    source_tier = "client session context"

            # Tier 3: Project Declarative Binding
            if not chosen_name and project_config:
                proj_val = project_config.profile_bindings.get(clean_server)
                if proj_val:
                    chosen_name = proj_val.strip()
                    source_tier = "project binding"

            # Tier 4: Server Default Profile
            if not chosen_name:
                if manifest.default_profile:
                    chosen_name = manifest.default_profile.strip()
                    source_tier = "server default"

            if not chosen_name:
                raise ProfileNotFoundError(
                    f"No profile specified and no default_profile configured for server '{server}'."
                )

            # Strict Invariant: Missing higher-priority profile reference must fail explicitly
            if chosen_name not in manifest.profiles:
                raise ProfileNotFoundError(
                    f"Profile '{chosen_name}' specified via {source_tier} does not exist for server '{server}'. "
                    f"Available profiles: {list(manifest.profiles.keys())}"
                )

            # Check if referenced secrets have rotated since last generation
            self._check_secret_rotation_under_lock(clean_server, chosen_name, manifest.profiles[chosen_name])

            gen = self._generations.get(clean_server, 1)
            # Return defensive snapshot so caller cannot mutate internal registry state
            return copy.deepcopy(manifest.profiles[chosen_name]), gen

    def _check_secret_rotation_under_lock(self, server: str, pname: str, profile: ProfileConfig) -> None:
        """Check if any secret for this profile rotated; increment generation if so."""
        rotated = False
        for sname, sref in profile.secrets.items():
            key = (server, f"{pname}:{sname}")
            old_ver = self._secret_versions.get(key)
            new_ver = self._secrets.get_secret_version(sref)
            if old_ver != new_ver:
                rotated = True
                self._secret_versions[key] = new_ver

        if rotated:
            self._generations[server] = self._generations.get(server, 1) + 1


# Global profile manager singleton
GLOBAL_PROFILE_MANAGER = ProfileManager()
