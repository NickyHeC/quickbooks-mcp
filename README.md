# quickbooks-mcp

A [QuickBooks Online](https://quickbooks.intuit.com) MCP server built on the [Dedalus](https://dedaluslabs.ai) platform.

Provides full access to QuickBooks Online accounting data — invoices, customers, vendors, bills, payments, accounts, items, estimates, and financial reports — through 20 MCP tools.

## Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/)
- A QuickBooks developer account with an OAuth2 application
- A [Dedalus](https://dedaluslabs.ai) account

---

## Quick Start

### 1. Create a QuickBooks OAuth Application

1. Go to the [Intuit Developer Portal](https://developer.intuit.com) and sign in.
2. Navigate to **Dashboard → Create an App** and select **QuickBooks Online and Payments**.
3. Under **Keys & OAuth**, note your **Client ID** and **Client Secret**.
4. Add the following **Redirect URI**:
   ```
   https://as.dedaluslabs.ai/oauth/callback
   ```
5. Note your **Realm ID** (Company ID) — it's shown during the OAuth playground flow or in the URL when viewing your sandbox company.

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Fill in your `.env`:

```env
# Dedalus Platform
DEDALUS_AS_URL=https://as.dedaluslabs.ai
DEDALUS_API_KEY=<your-dedalus-api-key>
DEDALUS_API_URL=https://api.dedaluslabs.ai

# QuickBooks
QBO_ACCESS_TOKEN=
QBO_REALM_ID=<your-company-realm-id>
QBO_ENVIRONMENT=sandbox

# QuickBooks OAuth (consumed by the Dedalus platform during deployment)
OAUTH_ENABLED=true
OAUTH_AUTHORIZE_URL=https://appcenter.intuit.com/connect/oauth2
OAUTH_TOKEN_URL=https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer
OAUTH_CLIENT_ID=<your-qbo-client-id>
OAUTH_CLIENT_SECRET=<your-qbo-client-secret>
OAUTH_SCOPES_AVAILABLE=com.intuit.quickbooks.accounting,com.intuit.quickbooks.payment
OAUTH_BASE_URL=https://quickbooks.api.intuit.com
```

### 3. Deploy to Dedalus

1. Log in to the [Dedalus Dashboard](https://dedaluslabs.ai).
2. Go to **Add Server** and connect this GitHub repository.
3. In the server configuration, enter the environment variables from your `.env` (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `QBO_REALM_ID`, etc.).
4. Deploy. The dashboard will show your server slug (e.g. `your-org/quickbooks-mcp`).

### 4. Install Dependencies

```bash
uv sync
```

### 5. Run Locally

```bash
uv run src/main.py
```

The server starts on port 8080.

---

## Environment Variables

### QuickBooks OAuth (server-side, set during Dedalus deployment)

| Variable | Description |
| --- | --- |
| `OAUTH_ENABLED` | `true` |
| `OAUTH_AUTHORIZE_URL` | `https://appcenter.intuit.com/connect/oauth2` |
| `OAUTH_TOKEN_URL` | `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer` |
| `OAUTH_CLIENT_ID` | Your QuickBooks OAuth app client ID |
| `OAUTH_CLIENT_SECRET` | Your QuickBooks OAuth app client secret |
| `OAUTH_SCOPES_AVAILABLE` | `com.intuit.quickbooks.accounting,com.intuit.quickbooks.payment` |
| `OAUTH_BASE_URL` | `https://quickbooks.api.intuit.com` |

### QuickBooks Configuration

| Variable | Description |
| --- | --- |
| `QBO_ACCESS_TOKEN` | OAuth access token (managed by DAuth in production) |
| `QBO_REALM_ID` | Company ID — required in every API URL |
| `QBO_ENVIRONMENT` | `sandbox` or `production` (default: `production`) |

### Dedalus Platform

| Variable | Description |
| --- | --- |
| `DEDALUS_API_KEY` | Your Dedalus API key (`dsk-*`) |
| `DEDALUS_API_URL` | API base URL (default: `https://api.dedaluslabs.ai`) |
| `DEDALUS_AS_URL` | Authorization server URL (default: `https://as.dedaluslabs.ai`) |

---

## Available Tools

| Tool | R/W | Description |
| --- | --- | --- |
| `query_entities` | R | SQL-like query for any entity (`SELECT * FROM Customer WHERE ...`) |
| `get_company_info` | R | Company name, address, fiscal year, and settings |
| `get_customer` | R | Get a customer by ID |
| `create_customer` | W | Create a new customer (DisplayName required) |
| `update_customer` | W | Update a customer (requires ID and SyncToken) |
| `get_invoice` | R | Get an invoice by ID |
| `create_invoice` | W | Create an invoice (CustomerRef and Line items required) |
| `send_invoice` | W | Email an invoice to the customer |
| `get_vendor` | R | Get a vendor by ID |
| `create_vendor` | W | Create a new vendor (DisplayName required) |
| `get_bill` | R | Get a bill by ID |
| `create_bill` | W | Create a bill (VendorRef and Line items required) |
| `get_payment` | R | Get a payment by ID |
| `create_payment` | W | Record a customer payment (CustomerRef and TotalAmt required) |
| `get_account` | R | Get a chart-of-accounts entry by ID |
| `get_item` | R | Get a product/service item by ID |
| `get_estimate` | R | Get an estimate (quote) by ID |
| `create_estimate` | W | Create an estimate (CustomerRef and Line items required) |
| `get_report` | R | Run a financial report (ProfitAndLoss, BalanceSheet, etc.) |
| `cdc` | R | Change Data Capture — entities changed since a timestamp |

---

## Architecture

QuickBooks Online exposes a RESTful JSON API where every request is scoped to a
company via its `realmId`. All requests are pinned to `minorversion=75`.

```
src/
├── config.py    # DAuth Connection + shared constants (realm ID, base URL)
├── main.py      # MCPServer setup and entry point
├── tools.py     # All 20 MCP tools + request helper
└── client.py    # Test client (connection test + tool test)
```

---

## Troubleshooting

### "Invalid redirect_uri parameter"

QuickBooks rejected the OAuth callback URL. Add `https://as.dedaluslabs.ai/oauth/callback`
to your app's **Redirect URIs** in the [Intuit Developer Portal](https://developer.intuit.com).

### SyncToken errors on updates

All update operations require the current `SyncToken` from the entity. Fetch the
entity first with the corresponding `get_*` tool, then pass the `SyncToken` value
to the update tool. Stale SyncTokens return a 400 error.

### Rate limiting (HTTP 429)

QuickBooks allows 500 requests/minute per company. Report endpoints have a tighter
limit of 200 requests/minute. The server uses exponential backoff with jitter on
429 responses.

### Access token expired

Access tokens expire after 60 minutes. In production, DAuth handles token refresh
automatically. For local testing, obtain a fresh token from the
[Intuit OAuth Playground](https://developer.intuit.com/app/developer/playground).

---

## Notes

- Uses the QBO SQL-like query language (`SELECT * FROM Invoice WHERE TotalAmt > 1000`).
- All API requests are pinned to `minorversion=75` (versions 1–74 were deprecated August 2025).
- Supports both sandbox and production environments via the `QBO_ENVIRONMENT` variable.
- Report responses are capped at 400,000 cells — large reports may be silently truncated.
- Pagination uses `STARTPOSITION` and `MAXRESULTS` (max 1000 per page, not cursor-based).
- Authentication uses OAuth 2.0 via DAuth. Direct API keys are not supported by QuickBooks.
