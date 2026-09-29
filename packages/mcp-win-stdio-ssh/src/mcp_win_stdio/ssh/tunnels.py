"""
SSH Port Forwarding & Tunneling Manager for mcp-win-stdio-ssh.
Allows creating background local-to-remote tunnels using paramiko direct-tcpip channels.
"""

import select
import socket
import socketserver
import threading
import time
from typing import Any, Dict, List, Optional

import paramiko

from mcp_win_stdio.ssh.connection import get_cached_or_connect, resolve_host_info

_ACTIVE_TUNNELS: Dict[str, Dict[str, Any]] = {}
_TUNNEL_LOCK = threading.RLock()


class ForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            chan = self.ssh_transport.open_channel(
                "direct-tcpip",
                (self.chain_host, self.chain_port),
                self.request.getpeername(),
            )
        except Exception:
            return

        if chan is None:
            return

        while True:
            r, w, x = select.select([self.request, chan], [], [])
            if self.request in r:
                data = self.request.recv(1024)
                if len(data) == 0:
                    break
                chan.send(data)
            if chan in r:
                data = chan.recv(1024)
                if len(data) == 0:
                    break
                self.request.send(data)

        chan.close()
        self.request.close()


def open_local_tunnel(
    local_port: int,
    remote_port: int,
    remote_host: str = "localhost",
    tunnel_name: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Start local port forwarding tunnel in a background thread."""
    host_info = resolve_host_info(host)
    client = get_cached_or_connect(host_info["name"])
    transport = client.get_transport()

    if not transport or not transport.is_active():
        raise ConnectionError(f"SSH connection to '{host_info['name']}' is not active.")

    name = tunnel_name or f"tunnel-{local_port}-to-{remote_host}-{remote_port}"

    with _TUNNEL_LOCK:
        if name in _ACTIVE_TUNNELS:
            return {
                "success": True,
                "message": f"Tunnel '{name}' is already active.",
                "tunnel": _ACTIVE_TUNNELS[name]["info"],
            }

        class CustomHandler(ForwardHandler):
            chain_host = remote_host
            chain_port = remote_port
            ssh_transport = transport

        try:
            server = ForwardServer(("127.0.0.1", local_port), CustomHandler)
        except Exception as e:
            raise OSError(f"Failed to bind local port {local_port}: {e}")

        server_thread = threading.Thread(
            target=server.serve_forever, daemon=True, name=f"SSHTunnel-{name}"
        )
        server_thread.start()

        info = {
            "name": name,
            "localPort": local_port,
            "localAddress": f"127.0.0.1:{local_port}",
            "remoteHost": remote_host,
            "remotePort": remote_port,
            "sshHost": host_info["name"],
            "status": "active",
            "startedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        _ACTIVE_TUNNELS[name] = {
            "server": server,
            "thread": server_thread,
            "info": info,
        }

        return {
            "success": True,
            "message": f"SSH Tunnel '{name}' established on 127.0.0.1:{local_port} -> {remote_host}:{remote_port} via {host_info['name']}.",
            "tunnel": info,
        }


def list_active_tunnels() -> List[Dict[str, Any]]:
    """List all currently active SSH port forwarding tunnels."""
    with _TUNNEL_LOCK:
        return [entry["info"] for entry in _ACTIVE_TUNNELS.values()]


def close_tunnel(tunnel_id_or_name: str) -> Dict[str, Any]:
    """Close an active port forwarding tunnel."""
    with _TUNNEL_LOCK:
        # Check by name or local port
        target_key = None
        for k, v in _ACTIVE_TUNNELS.items():
            if k == tunnel_id_or_name or str(v["info"]["localPort"]) == str(tunnel_id_or_name):
                target_key = k
                break

        if not target_key:
            return {
                "error": True,
                "message": f"Tunnel '{tunnel_id_or_name}' not found. Active tunnels: {list(_ACTIVE_TUNNELS.keys())}",
            }

        entry = _ACTIVE_TUNNELS.pop(target_key)
        try:
            entry["server"].shutdown()
            entry["server"].server_close()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Tunnel '{target_key}' closed successfully.",
        }


def close_all_tunnels() -> int:
    """Close all open tunnels."""
    closed = 0
    with _TUNNEL_LOCK:
        for k in list(_ACTIVE_TUNNELS.keys()):
            entry = _ACTIVE_TUNNELS.pop(k)
            try:
                entry["server"].shutdown()
                entry["server"].server_close()
                closed += 1
            except Exception:
                pass
    return closed
