"""
Interactive configuration wizard for mcp-win-stdio.
Provides secure interactive credential setup, field-by-field entry,
native Windows file/folder dialog integration, and ~/.mcp-win-stdio/ persistence.
"""

import getpass
import json
import os
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import (
    DB_CONNECTIONS_FILE,
    GIT_REPOS_FILE,
    KEYS_DIR,
    RAG_DATA_DIR,
    SERVER_CACHE_FILE,
    SERVER_CUSTOM_FILE,
    SSH_HOSTS_FILE,
    TSC_PROJECTS_FILE,
    USER_DIR,
    ensure_workspace_dirs,
)
from mcp_win_stdio.core.dialogs import prompt_path_or_dialog

# ============================================================================
# Helpers
# ============================================================================

def _read_json_safe(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_safe(path: Path, data: Dict[str, Any]) -> None:
    ensure_workspace_dirs()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _mask_url_password(url: str) -> str:
    """Mask password in connection URL for safe console display."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.password:
            masked_netloc = parsed.netloc.replace(f":{parsed.password}@", ":******@")
            return urllib.parse.urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        pass
    return url


# ============================================================================
# Database Configuration Wizard
# ============================================================================

def configure_database_wizard() -> None:
    """Interactive wizard for configuring PostgreSQL, MySQL, and SQLite databases."""
    ensure_workspace_dirs()
    print("\n" + "=" * 65)
    print("   🗄️  Database Configuration Wizard (db & excel-db)")
    print("=" * 65)
    print("Persistent store: ~/.mcp-win-stdio/db_connections.json")
    print("No environment variables required!\n")

    data = _read_json_safe(DB_CONNECTIONS_FILE)
    conns = data.get("connections", {})
    if not isinstance(conns, dict):
        conns = {k: v for k, v in data.items() if k not in ("default", "active_connection") and isinstance(v, (str, dict))}
        data = {"default": data.get("default"), "connections": conns}

    active = data.get("active_connection") or data.get("default")

    print("Current Configured Connections:")
    if not conns:
        print("  (None configured yet)")
    else:
        for alias, conn_val in conns.items():
            url_str = conn_val if isinstance(conn_val, str) else conn_val.get("url", str(conn_val))
            active_marker = " [ACTIVE DEFAULT]" if alias == active else ""
            print(f"  • {alias:<16} -> {_mask_url_password(url_str)}{active_marker}")

    print("\nActions:")
    print("  [1] Add new connection (URL or field-by-field)")
    print("  [2] Set active default connection")
    print("  [3] Remove a connection")
    print("  [4] Test a connection")
    print("  [5] Return to Main Menu")

    choice = input("\nSelect action (1-5) [default: 1]: ").strip() or "1"

    if choice == "1":
        _add_database_connection(data, conns)
    elif choice == "2":
        _set_active_database_connection(data, conns)
    elif choice == "3":
        _remove_database_connection(data, conns)
    elif choice == "4":
        _test_database_connection(conns)
    elif choice == "5":
        return
    else:
        print("Invalid choice.")


def _add_database_connection(data: Dict[str, Any], conns: Dict[str, Any]) -> None:
    print("\nConnection Entry Method:")
    print("  [1] Full Connection String (e.g. postgresql://user:pass@host:5432/dbname)")
    print("  [2] Field-by-field wizard (Host, Port, User, Password, DB)")
    print("  [3] SQLite Database file (Pick via Windows File Dialog)")

    method = input("\nSelect method (1-3) [default: 2]: ").strip() or "2"

    url = ""
    alias_default = ""

    if method == "1":
        raw = input("\nEnter Connection URL: ").strip().strip("\"'")
        if not raw:
            print("URL cannot be empty.")
            return
        url = raw
        try:
            parsed = urllib.parse.urlsplit(url)
            alias_default = parsed.path.lstrip("/").split("?")[0] or "db1"
        except Exception:
            alias_default = "db1"

    elif method == "3":
        file_path = prompt_path_or_dialog(
            prompt_label="Select SQLite Database File",
            is_directory=False,
            title="Select SQLite Database File (*.sqlite, *.db)",
            filetypes=[("SQLite Databases", "*.sqlite;*.db;*.sqlite3"), ("All Files", "*.*")],
        )
        if not file_path:
            print("File selection cancelled.")
            return
        clean_path = Path(file_path).as_posix()
        url = f"sqlite:///{clean_path}"
        alias_default = Path(file_path).stem

    else:
        print("\nSelect Database Engine:")
        print("  [1] PostgreSQL (default port: 5432)")
        print("  [2] MySQL / MariaDB (default port: 3306)")
        print("  [3] SQL Server (default port: 1433)")
        eng_choice = input("Engine (1-3) [default: 1]: ").strip() or "1"

        if eng_choice == "2":
            scheme = "mysql+pymysql"
            def_port = "3306"
            def_user = "root"
        elif eng_choice == "3":
            scheme = "mssql+pyodbc"
            def_port = "1433"
            def_user = "sa"
        else:
            scheme = "postgresql"
            def_port = "5432"
            def_user = "postgres"

        host = input("Host [default: 127.0.0.1]: ").strip() or "127.0.0.1"
        port = input(f"Port [default: {def_port}]: ").strip() or def_port
        dbname = input("Database Name: ").strip()
        if not dbname:
            print("Database name cannot be empty.")
            return

        user = input(f"Username [default: {def_user}]: ").strip() or def_user
        password = getpass.getpass("Password (masked): ")

        enc_user = urllib.parse.quote_plus(user)
        enc_pass = urllib.parse.quote_plus(password)
        url = f"{scheme}://{enc_user}:{enc_pass}@{host}:{port}/{dbname}"
        alias_default = dbname

    alias = input(f"\nConnection Alias Name [default: {alias_default}]: ").strip() or alias_default
    alias = alias.strip().replace(" ", "_")

    # Persist
    conns[alias] = url
    data["connections"] = conns

    # Default if first or chosen
    if len(conns) == 1 or not data.get("default"):
        data["default"] = alias
        data["active_connection"] = alias
    else:
        set_active = input(f"Set '{alias}' as active default connection? (y/N) [y]: ").strip().lower() != "n"
        if set_active:
            data["default"] = alias
            data["active_connection"] = alias

    _write_json_safe(DB_CONNECTIONS_FILE, data)
    print(f"\n✅ Connection '{alias}' saved to ~/.mcp-win-stdio/db_connections.json")

    # Offer to test
    do_test = input("Test connection reachability now? (y/N) [y]: ").strip().lower() != "n"
    if do_test:
        _run_db_test(url)


def _set_active_database_connection(data: Dict[str, Any], conns: Dict[str, Any]) -> None:
    if not conns:
        print("No connections configured.")
        return
    print("\nSelect connection to set as active default:")
    keys = list(conns.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            data["default"] = target
            data["active_connection"] = target
            _write_json_safe(DB_CONNECTIONS_FILE, data)
            print(f"✅ Active default connection set to: {target}")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


def _remove_database_connection(data: Dict[str, Any], conns: Dict[str, Any]) -> None:
    if not conns:
        print("No connections configured.")
        return
    print("\nSelect connection to remove:")
    keys = list(conns.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            conns.pop(target, None)
            data["connections"] = conns
            if data.get("default") == target or data.get("active_connection") == target:
                data["default"] = next(iter(conns.keys()), None)
                data["active_connection"] = data["default"]
            _write_json_safe(DB_CONNECTIONS_FILE, data)
            print(f"✅ Connection '{target}' removed.")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


def _test_database_connection(conns: Dict[str, Any]) -> None:
    if not conns:
        print("No connections configured.")
        return
    print("\nSelect connection to test:")
    keys = list(conns.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}) [1]: ").strip() or "1"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            val = conns[target]
            url = val if isinstance(val, str) else val.get("url", "")
            _run_db_test(url)
    except ValueError:
        print("Invalid number.")


def _run_db_test(url: str) -> None:
    print(f"\n🔍 Testing connection to: {_mask_url_password(url)} ...")
    try:
        import time
        from urllib.parse import urlsplit

        scheme = urlsplit(url).scheme.lower()
        t0 = time.perf_counter()

        if "sqlite" in scheme:
            import sqlite3
            path = urlsplit(url).path
            if sys.platform == "win32" and path.startswith("/"):
                path = path[1:]
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            dt = (time.perf_counter() - t0) * 1000
            print(f"✅ Connected to SQLite database successfully in {dt:.1f}ms!")

        elif "postgres" in scheme:
            try:
                import psycopg2
                conn = psycopg2.connect(url, connect_timeout=5)
                cur = conn.cursor()
                cur.execute("SELECT version();")
                v = cur.fetchone()[0]
                cur.close()
                conn.close()
                dt = (time.perf_counter() - t0) * 1000
                print(f"✅ Connected to PostgreSQL successfully in {dt:.1f}ms!")
                print(f"   Server Version: {v[:60]}...")
            except ImportError:
                print("⚠️  psycopg2 is not installed. To test live PostgreSQL connections:")
                print("   pip install psycopg2-binary")

        elif "mysql" in scheme:
            try:
                import pymysql
                parts = urlsplit(url)
                conn = pymysql.connect(
                    host=parts.hostname or "127.0.0.1",
                    port=parts.port or 3306,
                    user=parts.username or "root",
                    password=parts.password or "",
                    database=parts.path.lstrip("/") or None,
                    connect_timeout=5,
                )
                cur = conn.cursor()
                cur.execute("SELECT VERSION();")
                v = cur.fetchone()[0]
                cur.close()
                conn.close()
                dt = (time.perf_counter() - t0) * 1000
                print(f"✅ Connected to MySQL successfully in {dt:.1f}ms!")
                print(f"   Server Version: {v}")
            except ImportError:
                print("⚠️  pymysql is not installed. To test live MySQL connections:")
                print("   pip install pymysql")

        else:
            print(f"⚠️  Engine '{scheme}' reachability test not implemented directly, but configuration is saved.")
    except Exception as e:
        print(f"❌ Connection failed: {e}")


# ============================================================================
# SSH Configuration Wizard
# ============================================================================

def configure_ssh_wizard() -> None:
    """Interactive wizard for configuring SSH remote hosts and private keys."""
    ensure_workspace_dirs()
    print("\n" + "=" * 65)
    print("   🌐  SSH Remote Host Configuration Wizard (ssh MCP)")
    print("=" * 65)
    print("Persistent store: ~/.mcp-win-stdio/ssh_hosts.json")
    print("Secure Keys store: ~/.mcp-win-stdio/keys/\n")

    data = _read_json_safe(SSH_HOSTS_FILE)
    hosts = data.get("hosts", {})
    if not isinstance(hosts, dict):
        hosts = {}
        data["hosts"] = hosts

    active = data.get("active_host")

    print("Current Configured SSH Hosts:")
    if not hosts:
        print("  (None configured yet)")
    else:
        for alias, hdata in hosts.items():
            if isinstance(hdata, dict):
                user = hdata.get("user") or "default"
                hname = hdata.get("hostname") or alias
                port = hdata.get("port", 22)
                auth_desc = "Key: " + Path(hdata["key_path"]).name if hdata.get("key_path") else ("Password" if hdata.get("password") else "Default/Agent")
                active_marker = " [ACTIVE DEFAULT]" if alias == active else ""
                print(f"  • {alias:<14} -> {user}@{hname}:{port} ({auth_desc}){active_marker}")

    print("\nActions:")
    print("  [1] Add new SSH host (Select PEM key via Windows dialog or password)")
    print("  [2] Set active default host")
    print("  [3] Remove an SSH host")
    print("  [4] Test host reachability (ping/ssh handshake)")
    print("  [5] Return to Main Menu")

    choice = input("\nSelect action (1-5) [default: 1]: ").strip() or "1"

    if choice == "1":
        _add_ssh_host(data, hosts)
    elif choice == "2":
        _set_active_ssh_host(data, hosts)
    elif choice == "3":
        _remove_ssh_host(data, hosts)
    elif choice == "4":
        _test_ssh_host(hosts)
    elif choice == "5":
        return
    else:
        print("Invalid choice.")


def _add_ssh_host(data: Dict[str, Any], hosts: Dict[str, Any]) -> None:
    alias = input("\nUnique Host Alias (e.g. prod-api, dev-box): ").strip()
    if not alias:
        print("Alias cannot be empty.")
        return
    alias = alias.replace(" ", "_")

    hostname = input("Hostname or IP address: ").strip()
    if not hostname:
        print("Hostname cannot be empty.")
        return

    port_str = input("SSH Port [default: 22]: ").strip() or "22"
    try:
        port = int(port_str)
    except ValueError:
        port = 22

    user = input(f"Username [default: {getpass.getuser()}]: ").strip() or getpass.getuser()

    print("\nAuthentication Type:")
    print("  [1] Private Key (.pem, .id_rsa, .key) - Recommended")
    print("  [2] Plaintext Password")
    print("  [3] System SSH Agent / ~/.ssh/config default")

    auth_choice = input("Select (1-3) [default: 1]: ").strip() or "1"
    key_path = None
    password = None
    passphrase = None

    if auth_choice == "1":
        picked_key = prompt_path_or_dialog(
            prompt_label="Select SSH Private Key File",
            is_directory=False,
            title="Select SSH Private Key (*.pem, *.key, id_rsa)",
            filetypes=[("SSH Private Keys", "*.pem;*.key;id_*;*.ppk"), ("All Files", "*.*")],
        )
        if not picked_key or not os.path.isfile(picked_key):
            print("No valid key file selected.")
            return

        # Offer to copy into ~/.mcp-win-stdio/keys/
        import_copy = input(f"Import copy securely into ~/.mcp-win-stdio/keys/{alias}.pem? (y/N) [y]: ").strip().lower() != "n"
        if import_copy:
            target_key = KEYS_DIR / f"{alias}.pem"
            try:
                shutil.copy2(picked_key, target_key)
                # Restrict permissions on Windows/POSIX if possible
                try:
                    os.chmod(target_key, 0o600)
                except Exception:
                    pass
                key_path = str(target_key.resolve())
                print(f"✅ Imported key to: {key_path}")
            except Exception as e:
                print(f"Warning: Could not copy key: {e}. Using original path.")
                key_path = str(Path(picked_key).resolve())
        else:
            key_path = str(Path(picked_key).resolve())

        has_passphrase = input("Is this key protected by a passphrase? (y/N) [n]: ").strip().lower() == "y"
        if has_passphrase:
            passphrase = getpass.getpass("Key Passphrase (masked): ")

    elif auth_choice == "2":
        password = getpass.getpass("SSH Password (masked): ")

    jump_host = input("JumpHost / Bastion alias (optional, press Enter to skip): ").strip() or None
    description = input("Description (optional): ").strip() or None

    host_entry: Dict[str, Any] = {
        "hostname": hostname,
        "port": port,
        "user": user,
    }
    if key_path:
        host_entry["key_path"] = key_path
    if password:
        host_entry["password"] = password
    if passphrase:
        host_entry["passphrase"] = passphrase
    if jump_host:
        host_entry["jump_host"] = jump_host
    if description:
        host_entry["description"] = description

    hosts[alias] = host_entry
    data["hosts"] = hosts

    if len(hosts) == 1 or not data.get("active_host"):
        data["active_host"] = alias
    else:
        set_active = input(f"Set '{alias}' as active default host? (y/N) [y]: ").strip().lower() != "n"
        if set_active:
            data["active_host"] = alias

    _write_json_safe(SSH_HOSTS_FILE, data)
    print(f"\n✅ SSH host '{alias}' saved to ~/.mcp-win-stdio/ssh_hosts.json")

    do_test = input("Test SSH connection now? (y/N) [y]: ").strip().lower() != "n"
    if do_test:
        _run_ssh_test(alias, host_entry)


def _set_active_ssh_host(data: Dict[str, Any], hosts: Dict[str, Any]) -> None:
    if not hosts:
        print("No hosts configured.")
        return
    print("\nSelect host to set as active default:")
    keys = list(hosts.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            data["active_host"] = target
            _write_json_safe(SSH_HOSTS_FILE, data)
            print(f"✅ Active default SSH host set to: {target}")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


def _remove_ssh_host(data: Dict[str, Any], hosts: Dict[str, Any]) -> None:
    if not hosts:
        print("No hosts configured.")
        return
    print("\nSelect host to remove:")
    keys = list(hosts.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            hosts.pop(target, None)
            data["hosts"] = hosts
            if data.get("active_host") == target:
                data["active_host"] = next(iter(hosts.keys()), None)
            _write_json_safe(SSH_HOSTS_FILE, data)
            print(f"✅ SSH host '{target}' removed.")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


def _test_ssh_host(hosts: Dict[str, Any]) -> None:
    if not hosts:
        print("No hosts configured.")
        return
    print("\nSelect host to test:")
    keys = list(hosts.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}) [1]: ").strip() or "1"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            _run_ssh_test(target, hosts[target])
    except ValueError:
        print("Invalid number.")


def _run_ssh_test(alias: str, host_entry: Dict[str, Any]) -> None:
    print(f"\n🔍 Testing SSH handshake for '{alias}' ({host_entry.get('hostname')}:{host_entry.get('port', 22)}) ...")
    try:
        import time

        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: Dict[str, Any] = {
            "hostname": host_entry.get("hostname"),
            "port": host_entry.get("port", 22),
            "username": host_entry.get("user"),
            "timeout": 5.0,
            "banner_timeout": 5.0,
        }
        if host_entry.get("key_path"):
            kwargs["key_filename"] = host_entry["key_path"]
        if host_entry.get("password"):
            kwargs["password"] = host_entry["password"]
        if host_entry.get("passphrase"):
            kwargs["passphrase"] = host_entry["passphrase"]

        t0 = time.perf_counter()
        client.connect(**kwargs)
        _stdin, stdout, _stderr = client.exec_command("echo '__mws_ok__'; uname -srm 2>/dev/null || ver")
        out = stdout.read().decode("utf-8", errors="replace").strip()
        client.close()
        dt = (time.perf_counter() - t0) * 1000

        print(f"✅ Connected to SSH host '{alias}' successfully in {dt:.1f}ms!")
        lines = [l for l in out.splitlines() if "__mws_ok__" not in l]
        if lines:
            print(f"   Remote OS Info: {lines[0]}")
    except ImportError:
        print("⚠️  paramiko is not installed. To test live SSH hosts:")
        print("   pip install paramiko")
    except Exception as e:
        print(f"❌ SSH connection failed: {e}")


# ============================================================================
# TypeScript Configuration Wizard
# ============================================================================

def configure_tsc_wizard() -> None:
    """Interactive wizard for TypeScript project directories & 0ms watcher cache."""
    ensure_workspace_dirs()
    print("\n" + "=" * 65)
    print("   🔷  TypeScript Configuration Wizard (tsc MCP)")
    print("=" * 65)
    print("Persistent store: ~/.mcp-win-stdio/tsc_projects.json\n")

    data = _read_json_safe(TSC_PROJECTS_FILE)
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        projects = {}
        data["projects"] = projects

    active = data.get("active_project")

    print("Current Configured TypeScript Projects:")
    if not projects:
        print("  (None configured yet)")
    else:
        for alias, pinfo in projects.items():
            if isinstance(pinfo, dict):
                p_path = pinfo.get("path") or str(pinfo)
                watched = " [Auto-watch]" if pinfo.get("auto_watch", True) else ""
                active_marker = " [ACTIVE DEFAULT]" if alias == active else ""
                print(f"  • {alias:<16} -> {p_path}{watched}{active_marker}")

    print("\nActions:")
    print("  [1] Add TypeScript project directory (Select via Windows Folder Dialog)")
    print("  [2] Set active default project")
    print("  [3] Remove a project")
    print("  [4] Return to Main Menu")

    choice = input("\nSelect action (1-4) [default: 1]: ").strip() or "1"

    if choice == "1":
        _add_tsc_project(data, projects)
    elif choice == "2":
        _set_active_tsc_project(data, projects)
    elif choice == "3":
        _remove_tsc_project(data, projects)
    elif choice == "4":
        return
    else:
        print("Invalid choice.")


def _add_tsc_project(data: Dict[str, Any], projects: Dict[str, Any]) -> None:
    picked_dir = prompt_path_or_dialog(
        prompt_label="Select TypeScript Project Directory",
        is_directory=True,
        title="Select TypeScript Project Directory (containing tsconfig.json)",
        default_path=os.getcwd(),
    )
    if not picked_dir or not os.path.isdir(picked_dir):
        print("No valid directory selected.")
        return

    resolved_dir = Path(picked_dir).resolve()
    tsconfig = resolved_dir / "tsconfig.json"
    if not tsconfig.exists():
        print(f"⚠️  Note: No tsconfig.json found directly in {resolved_dir}.")
        print("   The tsc compiler watcher will search subdirectories when launched.")

    default_alias = resolved_dir.name or "ts_project"
    alias = input(f"\nProject Alias Name [default: {default_alias}]: ").strip() or default_alias
    alias = alias.replace(" ", "_")

    auto_watch = input("Auto-watch with 0ms in-memory error cache? (y/N) [y]: ").strip().lower() != "n"

    projects[alias] = {
        "path": str(resolved_dir),
        "tsconfig": str(tsconfig) if tsconfig.exists() else None,
        "auto_watch": auto_watch,
    }
    data["projects"] = projects

    if len(projects) == 1 or not data.get("active_project"):
        data["active_project"] = alias
    else:
        set_active = input(f"Set '{alias}' as active default project? (y/N) [y]: ").strip().lower() != "n"
        if set_active:
            data["active_project"] = alias

    _write_json_safe(TSC_PROJECTS_FILE, data)
    print(f"\n✅ TypeScript project '{alias}' saved to ~/.mcp-win-stdio/tsc_projects.json")


def _set_active_tsc_project(data: Dict[str, Any], projects: Dict[str, Any]) -> None:
    if not projects:
        print("No projects configured.")
        return
    print("\nSelect project to set as active default:")
    keys = list(projects.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            data["active_project"] = target
            _write_json_safe(TSC_PROJECTS_FILE, data)
            print(f"✅ Active default project set to: {target}")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


def _remove_tsc_project(data: Dict[str, Any], projects: Dict[str, Any]) -> None:
    if not projects:
        print("No projects configured.")
        return
    print("\nSelect project to remove:")
    keys = list(projects.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}")
    choice = input(f"Enter number (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            target = keys[idx]
            projects.pop(target, None)
            data["projects"] = projects
            if data.get("active_project") == target:
                data["active_project"] = next(iter(projects.keys()), None)
            _write_json_safe(TSC_PROJECTS_FILE, data)
            print(f"✅ Project '{target}' removed.")
        else:
            print("Invalid index.")
    except ValueError:
        print("Invalid number.")


# ============================================================================
# Gateway Server Configuration Wizard
# ============================================================================

def configure_gateway_wizard() -> None:
    """Configure Unified Gateway settings (idle timeout, buffer limit, cache)."""
    ensure_workspace_dirs()
    print("\n" + "=" * 65)
    print("   ⚡  Unified Gateway Server Configuration (mws server)")
    print("=" * 65)
    print("Persistent store: ~/.mcp-win-stdio/server_custom.json\n")

    custom_data = _read_json_safe(SERVER_CUSTOM_FILE)

    print("Actions:")
    print("  [1] View Gateway Status & Settings")
    print("  [2] Configure Idle Shutdown Timeout (default: 600s)")
    print("  [3] Configure Response Truncation Limit (default: 120,000 chars)")
    print("  [4] Register External/Custom MCP Server in Gateway")
    print("  [5] Purge Server Schema Cache (~/.mcp-win-stdio/server_cache.json)")
    print("  [6] Return to Main Menu")

    choice = input("\nSelect action (1-6) [default: 1]: ").strip() or "1"

    if choice == "1":
        idle = custom_data.get("idle_timeout_seconds", 600)
        max_chars = custom_data.get("max_response_chars", 120000)
        ext = custom_data.get("external_servers", {})
        print("\nGateway Settings:")
        print(f"  • Idle Process Timeout:  {idle}s ({idle // 60}m)")
        print(f"  • Max Character Limit:   {max_chars:,} chars")
        print(f"  • Custom External MCPs:  {len(ext)} registered")
        for name, entry in ext.items():
            cmd = entry.get("command", "")
            args = " ".join(entry.get("args", []))
            print(f"     - {name}: {cmd} {args}")

    elif choice == "2":
        cur = custom_data.get("idle_timeout_seconds", 600)
        new_val = input(f"Enter Idle Process Timeout in seconds [current: {cur}]: ").strip()
        try:
            val = int(new_val)
            if val < 30:
                print("Timeout must be at least 30 seconds.")
                return
            custom_data["idle_timeout_seconds"] = val
            _write_json_safe(SERVER_CUSTOM_FILE, custom_data)
            print(f"✅ Idle timeout updated to {val}s.")
        except ValueError:
            print("Invalid integer.")

    elif choice == "3":
        cur = custom_data.get("max_response_chars", 120000)
        new_val = input(f"Enter Max Response Characters Limit [current: {cur}]: ").strip()
        try:
            val = int(new_val)
            if val < 5000:
                print("Character limit must be at least 5,000 characters.")
                return
            custom_data["max_response_chars"] = val
            _write_json_safe(SERVER_CUSTOM_FILE, custom_data)
            print(f"✅ Max character limit updated to {val:,} chars.")
        except ValueError:
            print("Invalid integer.")

    elif choice == "4":
        sname = input("Custom MCP Server Name (e.g. 'my-custom-mcp'): ").strip()
        if not sname:
            return
        cmd = input("Executable Command (e.g. npx, python, docker): ").strip()
        raw_args = input("Command Arguments (space separated): ").strip()
        args = raw_args.split() if raw_args else []
        desc = input("One-line Description: ").strip() or f"Custom external MCP {sname}"

        ext = custom_data.get("external_servers", {})
        ext[sname] = {
            "command": cmd,
            "args": args,
            "description": desc,
        }
        custom_data["external_servers"] = ext
        _write_json_safe(SERVER_CUSTOM_FILE, custom_data)
        print(f"✅ Custom MCP '{sname}' registered into Gateway.")

    elif choice == "5":
        if SERVER_CACHE_FILE.exists():
            SERVER_CACHE_FILE.unlink()
            print("✅ Server schema cache purged. Schemas will refresh dynamically on next launch.")
        else:
            print("Cache is already empty.")


# ============================================================================
# Central Dashboard: View All Configurations
# ============================================================================

def view_all_configurations() -> None:
    """Print complete summary of all persistent configurations in ~/.mcp-win-stdio/."""
    ensure_workspace_dirs()
    print("\n" + "=" * 76)
    print("   📋  Persistent Configurations Summary (~/.mcp-win-stdio/)")
    print("=" * 76)

    # 1. Databases
    db_data = _read_json_safe(DB_CONNECTIONS_FILE)
    db_conns = db_data.get("connections", {})
    db_active = db_data.get("active_connection") or db_data.get("default")
    print(f"\n[Databases: {len(db_conns)} configured] -> {DB_CONNECTIONS_FILE.name}")
    if not db_conns:
        print("   (None configured — run 'mws config db' to add)")
    else:
        for a, u in db_conns.items():
            url_str = u if isinstance(u, str) else u.get("url", str(u))
            act = " [ACTIVE]" if a == db_active else ""
            print(f"   • {a:<14} -> {_mask_url_password(url_str)}{act}")

    # 2. SSH Hosts
    ssh_data = _read_json_safe(SSH_HOSTS_FILE)
    ssh_hosts = ssh_data.get("hosts", {})
    ssh_active = ssh_data.get("active_host")
    print(f"\n[SSH Hosts: {len(ssh_hosts)} configured] -> {SSH_HOSTS_FILE.name}")
    if not ssh_hosts:
        print("   (None configured — run 'mws config ssh' to add)")
    else:
        for a, h in ssh_hosts.items():
            if isinstance(h, dict):
                act = " [ACTIVE]" if a == ssh_active else ""
                auth = "Key" if h.get("key_path") else ("Password" if h.get("password") else "Agent")
                print(f"   • {a:<14} -> {h.get('user', '')}@{h.get('hostname')}:{h.get('port', 22)} ({auth}){act}")

    # 3. TypeScript Projects
    tsc_data = _read_json_safe(TSC_PROJECTS_FILE)
    tsc_projects = tsc_data.get("projects", {})
    tsc_active = tsc_data.get("active_project")
    print(f"\n[TypeScript Projects: {len(tsc_projects)} configured] -> {TSC_PROJECTS_FILE.name}")
    if not tsc_projects:
        print("   (None configured — run 'mws config tsc' to add)")
    else:
        for a, p in tsc_projects.items():
            if isinstance(p, dict):
                act = " [ACTIVE]" if a == tsc_active else ""
                print(f"   • {a:<14} -> {p.get('path', '')}{act}")

    # 4. RAG Collections
    rag_colls = [d.name for d in RAG_DATA_DIR.iterdir() if d.is_dir()] if RAG_DATA_DIR.exists() else []
    print(f"\n[RAG Knowledge Stores: {len(rag_colls)} indexed] -> {RAG_DATA_DIR.name}")
    if not rag_colls:
        print("   (No local collections indexed yet)")
    else:
        for c in rag_colls[:5]:
            print(f"   • {c}")
        if len(rag_colls) > 5:
            print(f"   ... and {len(rag_colls) - 5} more")

    # 5. Keys Directory
    key_files = list(KEYS_DIR.glob("*")) if KEYS_DIR.exists() else []
    print(f"\n[Imported SSH Keys: {len(key_files)}] -> {KEYS_DIR.name}")
    for k in key_files:
        print(f"   • {k.name}")

    print("\n" + "=" * 76 + "\n")


# ============================================================================
# Main Config CLI Entry Point
# ============================================================================

def main_config_interactive(subcommand: Optional[str] = None) -> None:
    """Main routing entry point for 'mws config [subcommand]'."""
    ensure_workspace_dirs()

    if subcommand:
        sub = subcommand.lower().strip()
        if sub in ("db", "database", "sql"):
            configure_database_wizard()
            return
        elif sub in ("ssh", "remote", "hosts"):
            configure_ssh_wizard()
            return
        elif sub in ("tsc", "typescript", "ts"):
            configure_tsc_wizard()
            return
        elif sub in ("server", "gateway"):
            configure_gateway_wizard()
            return
        elif sub in ("list", "view", "status", "all"):
            view_all_configurations()
            return

    while True:
        print("\n" + "=" * 65)
        print("   ⚙️   mcp-win-stdio Interactive Configuration Hub")
        print("=" * 65)
        print("Central location: ~/.mcp-win-stdio/ (Zero environment variables)")
        print("\nSelect configuration domain:")
        print("  [1] Database Connections (PostgreSQL, MySQL, SQLite)")
        print("  [2] SSH Remote Hosts & Private PEM Keys")
        print("  [3] TypeScript Watcher Projects & tsconfig.json")
        print("  [4] Gateway Server Settings (Idle reaper, custom MCPs)")
        print("  [5] View all saved configurations")
        print("  [6] Exit")

        choice = input("\nEnter choice (1-6) [default: 5]: ").strip() or "5"

        if choice == "1":
            configure_database_wizard()
        elif choice == "2":
            configure_ssh_wizard()
        elif choice == "3":
            configure_tsc_wizard()
        elif choice == "4":
            configure_gateway_wizard()
        elif choice == "5":
            view_all_configurations()
        elif choice == "6":
            print("Done.")
            break
        else:
            print("Invalid choice.")
