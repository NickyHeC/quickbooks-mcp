"""QuickBooks connection configuration.

Defines the DAuth Connection and shared constants used by both the server
(main.py) and the tools (tools.py). Lives in its own module to avoid
circular imports.
"""

import os

from dotenv import load_dotenv
from dedalus_mcp.auth import Connection, SecretKeys

load_dotenv()

MINOR_VERSION = "75"

realm_id = os.getenv("QBO_REALM_ID", "")
environment = os.getenv("QBO_ENVIRONMENT", "production").lower()
base_url = (
    f"https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}"
    if environment == "sandbox"
    else f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
)

qbo_connection = Connection(
    name="quickbooks-mcp",
    secrets=SecretKeys(token="QBO_ACCESS_TOKEN"),
    base_url=base_url,
    auth_header_format="Bearer {api_key}",
)
