#!/usr/bin/env python3
"""
CLI entry point for mcp-win-stdio-rag.
"""

import argparse
import sys
from mcp_win_stdio.rag.server import mcp

def main():
    parser = argparse.ArgumentParser(description="mcp-win-stdio-rag MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport mechanism")
    parser.add_argument("--port", type=int, default=8000, help="Port for SSE transport")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
