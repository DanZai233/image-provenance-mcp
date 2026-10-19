"""Shared FastMCP application instance.

Every tool module (ours and the vendored pixel analyzers) registers onto this one
app, so the server exposes a single flat tool list.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("image-provenance")
