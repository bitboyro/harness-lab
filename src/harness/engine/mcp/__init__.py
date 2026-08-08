"""MCP client, covering both spec revisions."""

from .client import ListedTools, McpClient, McpError, detect_revision

__all__ = ["ListedTools", "McpClient", "McpError", "detect_revision"]
