#!/usr/bin/env python3
"""
CLI entry point for mcp-win-stdio-excel-db.
"""

import argparse
import sys
from mcp_win_stdio.excel_db.server import mcp

def main():
    parser = argparse.ArgumentParser(description="mcp-win-stdio-excel-db MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport")
    parser.add_argument("--port", type=int, default=8001, help="Port for SSE transport")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
