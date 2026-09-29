"""
SFTP File Operations and Directory Traversal for mcp-win-stdio-ssh.
Provides token-safe remote file reading, streaming writing, metadata inspection, and sync operations.
"""

from datetime import datetime
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import paramiko

from mcp_win_stdio.ssh.connection import get_cached_or_connect, resolve_host_info

_SFTP_CLIENTS: Dict[str, paramiko.SFTPClient] = {}
_SFTP_LOCK = threading.RLock()


def get_sftp_client(target_name: Optional[str] = None) -> Tuple[paramiko.SFTPClient, Dict[str, Any]]:
    """Retrieve an active SFTP client for target host or open a new one."""
    host_info = resolve_host_info(target_name)
    name = host_info["name"]

    with _SFTP_LOCK:
        if name in _SFTP_CLIENTS:
            sftp = _SFTP_CLIENTS[name]
            # Check if channel active
            if sftp.get_channel() and not sftp.get_channel().closed:
                return sftp, host_info
            try:
                sftp.close()
            except Exception:
                pass
            del _SFTP_CLIENTS[name]

        ssh_client = get_cached_or_connect(name)
        sftp = ssh_client.open_sftp()
        _SFTP_CLIENTS[name] = sftp
        return sftp, host_info


def format_file_mode(mode_int: int) -> str:
    """Convert integer file mode to unix string representation (e.g. -rwxr-xr-x)."""
    return stat.filemode(mode_int)


def list_remote_directory(
    remote_path: str = ".",
    limit: int = 100,
    offset: int = 0,
    filter: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List contents of a remote directory with detailed metadata and context window protection.
    
    Args:
        remote_path: Target directory path on remote server.
        limit: Max items to return per batch (default 100, max 250).
        offset: Starting offset for pagination (default 0).
        filter: Optional substring filter for filenames.
        host: Target SSH host (or active host).
    """
    sftp, host_info = get_sftp_client(host)

    target_path = remote_path.strip() or "."
    try:
        # Normalize path
        if target_path == ".":
            target_path = sftp.normalize(".")

        attr_list = sftp.listdir_attr(target_path)
        items = []

        clean_filter = filter.strip().lower() if filter else None

        for attr in sorted(attr_list, key=lambda a: (not stat.S_ISDIR(a.st_mode), a.filename.lower())):
            if clean_filter and clean_filter not in attr.filename.lower():
                continue

            is_dir = stat.S_ISDIR(attr.st_mode)
            is_symlink = stat.S_ISLNK(attr.st_mode)
            mtime_dt = datetime.fromtimestamp(attr.st_mtime) if attr.st_mtime else None

            items.append({
                "name": attr.filename,
                "type": "directory" if is_dir else ("symlink" if is_symlink else "file"),
                "sizeBytes": attr.st_size,
                "sizeFormatted": f"{attr.st_size / 1024:.1f} KB" if attr.st_size < 1024*1024 else f"{attr.st_size / (1024*1024):.2f} MB",
                "permissions": format_file_mode(attr.st_mode),
                "modified": mtime_dt.isoformat() if mtime_dt else None,
                "uid": attr.st_uid,
                "gid": attr.st_gid,
            })

        safe_limit = min(max(1, limit), 250)
        safe_offset = max(0, offset)
        total_items = len(items)
        display_items = items[safe_offset : safe_offset + safe_limit]
        has_more = total_items > (safe_offset + len(display_items))

        res: Dict[str, Any] = {
            "host": host_info["name"],
            "remotePath": target_path,
            "totalItems": total_items,
            "returnedItems": len(display_items),
            "offset": safe_offset,
            "limit": safe_limit,
            "hasMore": has_more,
            "truncated": has_more,
            "items": display_items,
        }

        if has_more:
            next_offset = safe_offset + len(display_items)
            res["notice"] = (
                f"... [TRUNCATED: Showing items {safe_offset + 1}-{next_offset} of {total_items}. "
                f"Use offset={next_offset} or provide 'filter' parameter to narrow search] ..."
            )

        return res
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": target_path,
            "message": f"Failed to list remote directory '{target_path}': {e}",
        }


def read_remote_text_file(
    remote_path: str,
    max_chars: int = 15000,
    offset_lines: int = 0,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Read a remote text file with line offset support and token safety."""
    sftp, host_info = get_sftp_client(host)

    try:
        with sftp.open(remote_path, "r") as f:
            lines = f.readlines()

        total_lines = len(lines)
        selected_lines = lines[offset_lines:] if offset_lines < total_lines else []
        content = "".join(selected_lines)

        is_truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            is_truncated = True

        return {
            "host": host_info["name"],
            "remotePath": remote_path,
            "totalLines": total_lines,
            "offsetLines": offset_lines,
            "linesReturned": len(selected_lines),
            "isTruncated": is_truncated,
            "content": content,
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "message": f"Failed to read remote file '{remote_path}': {e}",
        }


def write_remote_text_file(
    remote_path: str,
    content: str,
    mode: str = "write",
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Write or append text content to a remote file."""
    sftp, host_info = get_sftp_client(host)

    open_mode = "w" if mode == "write" else "a"
    try:
        # Ensure parent directories exist
        parent = str(Path(remote_path).parent).replace("\\", "/")
        if parent and parent != "." and parent != "/":
            _ensure_remote_dir(sftp, parent)

        with sftp.open(remote_path, open_mode) as f:
            f.write(content)

        return {
            "success": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "bytesWritten": len(content.encode("utf-8")),
            "mode": mode,
            "message": f"Successfully wrote {len(content.encode('utf-8'))} bytes to '{remote_path}' on {host_info['name']}.",
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "message": f"Failed to write to remote file '{remote_path}': {e}",
        }


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    """Helper to recursively create remote directories if missing."""
    parts = remote_dir.strip("/").split("/")
    cur = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        cur += part + "/"
        try:
            sftp.stat(cur)
        except IOError:
            try:
                sftp.mkdir(cur)
            except Exception:
                pass


def stat_remote_path(
    remote_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect metadata, permissions, and stats for a remote path."""
    sftp, host_info = get_sftp_client(host)

    try:
        st = sftp.stat(remote_path)
        is_dir = stat.S_ISDIR(st.st_mode)
        is_file = stat.S_ISREG(st.st_mode)
        is_sym = stat.S_ISLNK(st.st_mode)
        mtime_dt = datetime.fromtimestamp(st.st_mtime) if st.st_mtime else None
        atime_dt = datetime.fromtimestamp(st.st_atime) if st.st_atime else None

        return {
            "host": host_info["name"],
            "remotePath": remote_path,
            "exists": True,
            "isDirectory": is_dir,
            "isFile": is_file,
            "isSymlink": is_sym,
            "sizeBytes": st.st_size,
            "permissions": format_file_mode(st.st_mode),
            "octalPermissions": oct(stat.S_IMODE(st.st_mode)),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "modified": mtime_dt.isoformat() if mtime_dt else None,
            "accessed": atime_dt.isoformat() if atime_dt else None,
        }
    except IOError:
        return {
            "host": host_info["name"],
            "remotePath": remote_path,
            "exists": False,
            "message": f"Path '{remote_path}' does not exist on '{host_info['name']}'.",
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "message": f"Failed to stat remote path '{remote_path}': {e}",
        }


def upload_path(
    local_path: str,
    remote_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a local file or folder to the remote host."""
    sftp, host_info = get_sftp_client(host)
    local_p = Path(local_path).resolve()

    if not local_p.exists():
        return {
            "error": True,
            "message": f"Local path '{local_path}' does not exist.",
        }

    try:
        if local_p.is_file():
            _ensure_remote_dir(sftp, str(Path(remote_path).parent).replace("\\", "/"))
            sftp.put(str(local_p), remote_path.replace("\\", "/"))
            return {
                "success": True,
                "host": host_info["name"],
                "localPath": str(local_p),
                "remotePath": remote_path,
                "sizeBytes": local_p.stat().st_size,
                "message": f"Uploaded '{local_p.name}' ({local_p.stat().st_size} bytes) to '{remote_path}' on {host_info['name']}.",
            }

        # Directory recursive upload
        uploaded_count = 0
        for root, dirs, files in os.walk(str(local_p)):
            rel_path = os.path.relpath(root, str(local_p))
            dest_dir = (Path(remote_path) / rel_path).as_posix() if rel_path != "." else remote_path.replace("\\", "/")
            _ensure_remote_dir(sftp, dest_dir)

            for f in files:
                src_file = Path(root) / f
                dst_file = f"{dest_dir.rstrip('/')}/{f}"
                sftp.put(str(src_file), dst_file)
                uploaded_count += 1

        return {
            "success": True,
            "host": host_info["name"],
            "localPath": str(local_p),
            "remotePath": remote_path,
            "filesUploaded": uploaded_count,
            "message": f"Recursively uploaded directory ({uploaded_count} files) to '{remote_path}' on {host_info['name']}.",
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "localPath": str(local_p),
            "remotePath": remote_path,
            "message": f"Upload failed: {e}",
        }


def download_path(
    remote_path: str,
    local_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Download a remote file or folder to the local machine."""
    sftp, host_info = get_sftp_client(host)
    local_p = Path(local_path).resolve()

    try:
        st = sftp.stat(remote_path)
        is_dir = stat.S_ISDIR(st.st_mode)

        if not is_dir:
            local_p.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote_path, str(local_p))
            return {
                "success": True,
                "host": host_info["name"],
                "remotePath": remote_path,
                "localPath": str(local_p),
                "sizeBytes": st.st_size,
                "message": f"Downloaded '{remote_path}' ({st.st_size} bytes) to '{local_p}'.",
            }

        # Recursive directory download
        downloaded_count = 0

        def _download_dir_recursive(rem_dir: str, loc_dir: Path):
            nonlocal downloaded_count
            loc_dir.mkdir(parents=True, exist_ok=True)
            for attr in sftp.listdir_attr(rem_dir):
                r_item = f"{rem_dir.rstrip('/')}/{attr.filename}"
                l_item = loc_dir / attr.filename
                if stat.S_ISDIR(attr.st_mode):
                    _download_dir_recursive(r_item, l_item)
                else:
                    sftp.get(r_item, str(l_item))
                    downloaded_count += 1

        _download_dir_recursive(remote_path, local_p)

        return {
            "success": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "localPath": str(local_p),
            "filesDownloaded": downloaded_count,
            "message": f"Recursively downloaded remote directory ({downloaded_count} files) to '{local_p}'.",
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "localPath": str(local_p),
            "message": f"Download failed: {e}",
        }


def remove_remote_path(
    remote_path: str,
    recursive: bool = False,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete a remote file or directory."""
    sftp, host_info = get_sftp_client(host)

    try:
        st = sftp.stat(remote_path)
        if stat.S_ISDIR(st.st_mode):
            if recursive:
                def _rm_recursive(rem_dir: str):
                    for attr in sftp.listdir_attr(rem_dir):
                        item = f"{rem_dir.rstrip('/')}/{attr.filename}"
                        if stat.S_ISDIR(attr.st_mode):
                            _rm_recursive(item)
                        else:
                            sftp.remove(item)
                    sftp.rmdir(rem_dir)
                _rm_recursive(remote_path)
            else:
                sftp.rmdir(remote_path)
        else:
            sftp.remove(remote_path)

        return {
            "success": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "message": f"Removed '{remote_path}' on {host_info['name']}.",
        }
    except Exception as e:
        return {
            "error": True,
            "host": host_info["name"],
            "remotePath": remote_path,
            "message": f"Failed to remove remote path '{remote_path}': {e}",
        }
