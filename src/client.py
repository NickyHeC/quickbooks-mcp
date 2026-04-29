"""Test client for the QuickBooks Online MCP server.

Two modes:

1. Test connection only (no server needed):
       python -m src.client --test-connection

2. Test tools (server must be running on port 8080):
       python -m src.main        # in one terminal
       python -m src.client      # in another
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()


async def test_connection() -> None:
    """Verify the DAuth connection and QBO credentials without a running server."""
    from dedalus_mcp.testing import ConnectionTester, TestRequest
    from src.config import qbo_connection

    tester = ConnectionTester.from_env(qbo_connection)
    from src.config import realm_id
    response = await tester.request(TestRequest(path=f"/companyinfo/{realm_id}"))

    if response.success:
        print(f"OK {response.status} — Connection works!")
        print(f"Response: {response.body}")
    else:
        print(f"FAIL {response.status}")
        print(f"Response: {response.body}")


async def test_tools() -> None:
    """Connect to the running server and call tools."""
    from dedalus_mcp.client import MCPClient

    client = await MCPClient.connect("http://127.0.0.1:8080/mcp")

    available = await client.list_tools()
    print("Available tools:", [t.name for t in available.tools])

    result = await client.call_tool(
        "query_entities",
        {"query": "SELECT * FROM Customer MAXRESULTS 5"},
    )
    print("query_entities result:", result.content[0].text)

    result = await client.call_tool("get_company_info", {})
    print("get_company_info result:", result.content[0].text)

    await client.close()


if __name__ == "__main__":
    if "--test-connection" in sys.argv:
        asyncio.run(test_connection())
    else:
        asyncio.run(test_tools())
