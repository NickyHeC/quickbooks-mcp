"""QuickBooks Online MCP server.

Provides AI assistants with full access to QuickBooks Online accounting data
via OAuth 2.0 and the Dedalus MCP framework with DAuth.
"""

import os
import asyncio

from dedalus_mcp import MCPServer
from dedalus_mcp.server import TransportSecuritySettings

from src.config import qbo_connection
from src.tools import tools


def create_server() -> MCPServer:
    as_url = os.getenv("DEDALUS_AS_URL", "https://as.dedaluslabs.ai")
    return MCPServer(
        name="quickbooks-mcp",
        connections=[qbo_connection],
        http_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        streamable_http_stateless=True,
        authorization_server=as_url,
    )


async def main() -> None:
    server = create_server()
    for tool_func in tools:
        server.collect(tool_func)
    await server.serve(port=8080)


if __name__ == "__main__":
    asyncio.run(main())
