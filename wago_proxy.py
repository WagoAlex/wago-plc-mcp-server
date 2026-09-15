"""stdio ↔ HTTP proxy so Claude Desktop can reach the MCP server.

Set WAGO_MCP_API_KEY in the claude_desktop_config.json env block when Bearer
auth is enabled on the server.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server import create_proxy

api_key = os.environ.get("WAGO_MCP_API_KEY", "")
url = os.environ.get("WAGO_MCP_URL", "http://localhost:6042/mcp")

client = Client(url, auth=BearerAuth(token=api_key)) if api_key else Client(url)

mcp = create_proxy(client, name="wago-plc")
mcp.run(transport="stdio")
