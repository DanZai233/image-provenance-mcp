"""Re-export the shared app so vendored modules register on the same server."""

from provenance_mcp.app import mcp

__all__ = ["mcp"]
