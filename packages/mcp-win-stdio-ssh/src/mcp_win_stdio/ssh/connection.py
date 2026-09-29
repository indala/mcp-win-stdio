"""
SSH Connection Pool and Host Configuration Manager for mcp-win-stdio-ssh.
Handles ~/.ssh/config auto-discovery, persistent host bookmarks, authentication resolution,
bastion/jump host tunneling, and resilient connection pooling.
"""

import json
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import paramiko
from paramiko.config import SSHConfig

from mcp_win_stdio.core.config import INDALA_DIR, ensure_workspace_dirs

SSH_CONFIG_DIR = INDALA_DIR
HOSTS_CONFIG_FILE = SSH_CONFIG_DIR / "ssh_hosts.json"
SSH_USER_DIR = Path.home() / ".ssh"
SYSTEM_SSH_CONFIG = SSH_USER_DIR / "config"

_ACTIVE_HOST: Optional[str] = None
_CLIENT_POOL: Dict[str, paramiko.SSHClient] = {}
_POOL_LOCK = threading.RLock()


def _normalize_host_param(host: Any) -> Optional[str]:
    """Normalize host parameter from LLM tool call, filtering out null/empty strings."""
    if host is None:
        return None
    s = str(host).strip()
    if s.lower() in ("", "null", "none", "undefined", "default"):
        return None
    return s


def load_ssh_hosts() -> Dict[str, Any]:
    """Load persistent SSH hosts from ~/.mcp-win-stdio/ssh_hosts.json."""
    ensure_workspace_dirs()
    if not HOSTS_CONFIG_FILE.exists():
        return {}
    try:
        with open(HOSTS_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_ssh_hosts(data: Dict[str, Any]) -> None:
    """Save persistent SSH hosts to ~/.mcp-win-stdio/ssh_hosts.json."""
    ensure_workspace_dirs()
    try:
        with open(HOSTS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to save ssh hosts: {e}\n")


def get_active_host_name() -> Optional[str]:
    """Get the currently active host name (memory or persistent)."""
    global _ACTIVE_HOST
    if _ACTIVE_HOST:
        return _ACTIVE_HOST
    data = load_ssh_hosts()
    active = data.get("active_host")
    if active:
        _ACTIVE_HOST = active
        return active
    return None


def set_active_host_name(name: Optional[str]) -> None:
    """Set and persist the active host name."""
    global _ACTIVE_HOST
    _ACTIVE_HOST = name
    data = load_ssh_hosts()
    data["active_host"] = name
    save_ssh_hosts(data)


def parse_system_ssh_config() -> Dict[str, Dict[str, Any]]:
    """Parse ~/.ssh/config and return a mapping of host aliases to connection configs."""
    configs: Dict[str, Dict[str, Any]] = {}
    if not SYSTEM_SSH_CONFIG.exists():
        return configs

    try:
        ssh_cfg = SSHConfig()
        with open(SYSTEM_SSH_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            ssh_cfg.parse(f)

        # Iterate through host entries
        for host in ssh_cfg.get_hostnames():
            if host == "*":
                continue
            entry = ssh_cfg.lookup(host)
            identity_files = entry.get("identityfile", [])
            key_path = identity_files[0] if identity_files else None
            
            # Resolve ~ in key path
            if key_path:
                key_path = str(Path(key_path).expanduser())

            configs[host] = {
                "name": host,
                "hostname": entry.get("hostname", host),
                "user": entry.get("user", os.environ.get("USERNAME", "root")),
                "port": int(entry.get("port", 22)),
                "key_path": key_path,
                "proxyjump": entry.get("proxyjump"),
                "proxycommand": entry.get("proxycommand"),
                "source": "ssh_config",
            }
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse system SSH config: {e}\n")

    return configs


def get_all_registered_hosts() -> Dict[str, Dict[str, Any]]:
    """Merge SSH config hosts, persistent custom hosts, and env variables."""
    all_hosts: Dict[str, Dict[str, Any]] = {}

    # 1. System ~/.ssh/config
    system_hosts = parse_system_ssh_config()
    all_hosts.update(system_hosts)

    # 2. Persistent ~/.mcp-win-stdio/ssh_hosts.json
    saved_data = load_ssh_hosts()
    hosts_dict = saved_data.get("hosts", {})
    for name, host_data in hosts_dict.items():
        if isinstance(host_data, dict):
            entry = dict(host_data)
            entry["name"] = name
            entry["source"] = "saved_config"
            all_hosts[name] = entry

    # 3. Environment variable SSH_SERVERS (JSON format)
    env_servers = os.environ.get("SSH_SERVERS")
    if env_servers:
        try:
            parsed = json.loads(env_servers)
            if isinstance(parsed, dict):
                for name, cfg in parsed.items():
                    if isinstance(cfg, dict):
                        entry = dict(cfg)
                        entry["name"] = name
                        entry["source"] = "env"
                        all_hosts[name] = entry
        except Exception:
            pass

    return all_hosts


def resolve_host_info(target_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolve connection parameters for a host by name or active default.
    Supports user@host:port strings or registered aliases.
    """
    norm = _normalize_host_param(target_name)
    host_name = norm or get_active_host_name()

    registered = get_all_registered_hosts()

    if host_name and host_name in registered:
        return registered[host_name]

    # Check if target is a direct user@hostname:port connection string
    if host_name and ("@" in host_name or "." in host_name):
        user = os.environ.get("USERNAME", "root")
        host_str = host_name
        port = 22

        if "@" in host_str:
            user, host_str = host_str.split("@", 1)

        if ":" in host_str:
            host_str, port_str = host_str.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 22

        return {
            "name": host_name,
            "hostname": host_str,
            "user": user,
            "port": port,
            "key_path": None,
            "source": "ad_hoc",
        }

    if not host_name:
        if registered:
            first_name = next(iter(registered.keys()))
            set_active_host_name(first_name)
            return registered[first_name]
        raise ValueError(
            "No SSH host specified and no active host is configured. "
            "Use 'add_host' or provide 'host' parameter."
        )

    raise ValueError(f"SSH host '{host_name}' not found. Available hosts: {list(registered.keys())}")


def _find_default_keys() -> List[str]:
    """Find default SSH keys in ~/.ssh/ directory."""
    keys = []
    if SSH_USER_DIR.is_dir():
        for key_name in ["id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"]:
            kp = SSH_USER_DIR / key_name
            if kp.exists():
                keys.append(str(kp))
    return keys


def create_ssh_client(
    host_info: Dict[str, Any],
    password: Optional[str] = None,
    passphrase: Optional[str] = None,
    timeout: int = 15,
) -> paramiko.SSHClient:
    """Instantiate and connect a paramiko.SSHClient based on host info."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    hostname = host_info.get("hostname", "localhost")
    port = int(host_info.get("port", 22))
    username = host_info.get("user") or os.environ.get("USERNAME", "root")
    key_path = host_info.get("key_path")
    pwd = password or host_info.get("password")
    pass_phrase = passphrase or host_info.get("passphrase")

    key_filename = None
    if key_path and Path(key_path).expanduser().exists():
        key_filename = str(Path(key_path).expanduser())
    else:
        # Check default keys
        default_keys = _find_default_keys()
        if default_keys:
            key_filename = default_keys[0]

    # Support JumpHost / Bastion if specified
    sock = None
    jump_host = host_info.get("jump_host") or host_info.get("proxyjump")
    if jump_host:
        jump_info = resolve_host_info(jump_host)
        jump_client = get_cached_or_connect(jump_info["name"])
        transport = jump_client.get_transport()
        if transport and transport.is_active():
            dest_addr = (hostname, port)
            local_addr = ("127.0.0.1", 0)
            sock = transport.open_channel("direct-tcpip", dest_addr, local_addr)

    connect_kwargs: Dict[str, Any] = {
        "hostname": hostname,
        "port": port,
        "username": username,
        "timeout": timeout,
        "allow_agent": True,
        "look_for_keys": True,
    }

    if sock:
        connect_kwargs["sock"] = sock
    if pwd:
        connect_kwargs["password"] = pwd
    if key_filename:
        connect_kwargs["key_filename"] = key_filename
    if pass_phrase:
        connect_kwargs["passphrase"] = pass_phrase

    try:
        client.connect(**connect_kwargs)
        # Enable keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        return client
    except Exception as e:
        client.close()
        raise ConnectionError(
            f"Failed to connect to SSH host '{host_info.get('name', hostname)}' ({username}@{hostname}:{port}): {e}"
        )


def get_cached_or_connect(
    target_name: Optional[str] = None,
    password: Optional[str] = None,
    passphrase: Optional[str] = None,
    timeout: int = 15,
) -> paramiko.SSHClient:
    """Retrieve an active SSH client from the pool or establish a new connection."""
    host_info = resolve_host_info(target_name)
    name = host_info["name"]

    with _POOL_LOCK:
        if name in _CLIENT_POOL:
            client = _CLIENT_POOL[name]
            transport = client.get_transport()
            if transport and transport.is_active():
                return client
            # Drop dead connection
            try:
                client.close()
            except Exception:
                pass
            del _CLIENT_POOL[name]

        client = create_ssh_client(
            host_info, password=password, passphrase=passphrase, timeout=timeout
        )
        _CLIENT_POOL[name] = client
        return client


def close_connection(target_name: Optional[str] = None) -> bool:
    """Close connection for a specific host in the pool."""
    norm = _normalize_host_param(target_name)
    name = norm or get_active_host_name()
    if not name:
        return False

    with _POOL_LOCK:
        if name in _CLIENT_POOL:
            try:
                _CLIENT_POOL[name].close()
            except Exception:
                pass
            del _CLIENT_POOL[name]
            return True
    return False


def close_all_connections() -> int:
    """Close all open SSH connections in the pool."""
    closed = 0
    with _POOL_LOCK:
        for name, client in list(_CLIENT_POOL.items()):
            try:
                client.close()
                closed += 1
            except Exception:
                pass
        _CLIENT_POOL.clear()
    return closed


def get_pool_status() -> List[Dict[str, Any]]:
    """Return status of all live connections in the pool."""
    status = []
    with _POOL_LOCK:
        for name, client in _CLIENT_POOL.items():
            transport = client.get_transport()
            is_active = transport.is_active() if transport else False
            status.append({
                "name": name,
                "isActive": is_active,
                "remoteAddress": f"{transport.getpeername()}" if (transport and is_active) else "closed",
                "isCurrentDefault": name == get_active_host_name(),
            })
    return status
