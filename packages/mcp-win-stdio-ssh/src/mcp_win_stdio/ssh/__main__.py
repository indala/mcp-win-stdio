"""
Direct execution entrypoint: python -m mcp_win_stdio.ssh
"""

from mcp_win_stdio.ssh.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
