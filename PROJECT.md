# PROJECT.md — Platform Research Notes

> This file is a working notepad for the developer (or AI coding agent) building
> this MCP server. Fill in each section as you research the target platform.
> The information here drives the implementation in `src/main.py` and `src/tools.py`.
>
> **Do not commit secrets.** Store credentials in `.env` (which is gitignored).

---

## Platform Overview

**Platform name:** QuickBooks Online (Intuit)
**Official docs:** https://developer.intuit.com/app/developer/qbo/docs/develop
**Base URL:** `https://quickbooks.api.intuit.com/v3/company/{realmId}/` (production), `https://sandbox-quickbooks.api.intuit.com/v3/company/{realmId}/` (sandbox)

QuickBooks Online is the dominant SMB accounting platform (62%+ market share) providing invoicing, expense tracking, payroll, and financial reporting. The QBO API is a RESTful JSON API organized around accounting entities (Invoices, Customers, Vendors, Bills, Payments, Accounts, etc.). Every request is scoped to a specific company via its `realmId`. Building an MCP server for QuickBooks enables AI assistants to query financial data, create invoices, manage customers/vendors, record payments, and generate reports programmatically.

---

## Authentication

**Auth type:** OAuth 2.0 (Authorization Code Flow)
**How to obtain credentials:** https://developer.intuit.com — register a developer account, create an app, get Client ID and Client Secret from the Keys & OAuth tab

### Credential details

- **Token / key name:** `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_REALM_ID`
- **Header format:** `Authorization: Bearer {access_token}` plus `Accept: application/json`
- **Scopes required:**
  - `com.intuit.quickbooks.accounting` — full access to all accounting entities and endpoints
  - `com.intuit.quickbooks.payment` — access to QuickBooks Payments API (processing payments)
  - `openid`, `email`, `profile` — optional, for user identity

### OAuth-specific

- **Authorize URL:** `https://appcenter.intuit.com/connect/oauth2?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=com.intuit.quickbooks.accounting&state={state}`
- **Token URL:** `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`
- **Client ID:** (store in `.env` as `QBO_CLIENT_ID`)
- **Client Secret:** (store in `.env` as `QBO_CLIENT_SECRET`)
- **Available scopes:** `com.intuit.quickbooks.accounting`, `com.intuit.quickbooks.payment`, `openid`, `email`, `profile`

### Example authenticated request

```bash
# Exchange authorization code for tokens
curl -X POST 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H "Authorization: Basic $(echo -n '$QBO_CLIENT_ID:$QBO_CLIENT_SECRET' | base64)" \
  -d 'grant_type=authorization_code&code=AUTH_CODE&redirect_uri=REDIRECT_URI'

# Query customers
curl 'https://quickbooks.api.intuit.com/v3/company/{realmId}/query?query=SELECT%20*%20FROM%20Customer%20MAXRESULTS%2010&minorversion=75' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Accept: application/json'

# Create an invoice
curl -X POST 'https://quickbooks.api.intuit.com/v3/company/{realmId}/invoice?minorversion=75' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "CustomerRef": {"value": "123"},
    "Line": [{
      "Amount": 500,
      "DetailType": "SalesItemLineDetail",
      "SalesItemLineDetail": {"ItemRef": {"value": "45"}}
    }]
  }'
```

---

## Endpoints / Features to Implement

List the API endpoints or features you plan to expose as MCP tools.
For each, note the HTTP method, path, key parameters, and response shape.

All paths are relative to `https://quickbooks.api.intuit.com/v3/company/{realmId}/`.

| Tool name | Method | Path | Description |
|-----------|--------|------|-------------|
| query_entities | GET | `/query?query={sql}` | SQL-like query for any entity (SELECT * FROM Customer WHERE ...). Primary read mechanism |
| get_company_info | GET | `/companyinfo/{realmId}` | Get company name, address, fiscal year, and settings |
| get_customer | GET | `/customer/{id}` | Retrieve a specific customer by ID |
| create_customer | POST | `/customer` | Create a new customer. Required: DisplayName |
| update_customer | POST | `/customer` | Update a customer (must include Id and SyncToken) |
| get_invoice | GET | `/invoice/{id}` | Retrieve a specific invoice by ID |
| create_invoice | POST | `/invoice` | Create a new invoice. Required: CustomerRef, Line items |
| send_invoice | POST | `/invoice/{id}/send` | Email an invoice to the customer |
| get_vendor | GET | `/vendor/{id}` | Retrieve a specific vendor by ID |
| create_vendor | POST | `/vendor` | Create a new vendor. Required: DisplayName |
| get_bill | GET | `/bill/{id}` | Retrieve a specific bill by ID |
| create_bill | POST | `/bill` | Create a new bill. Required: VendorRef, Line items |
| get_payment | GET | `/payment/{id}` | Retrieve a specific payment by ID |
| create_payment | POST | `/payment` | Record a customer payment. Required: CustomerRef, TotalAmt |
| get_account | GET | `/account/{id}` | Retrieve a chart-of-accounts entry by ID |
| get_item | GET | `/item/{id}` | Retrieve a product/service item by ID |
| get_estimate | GET | `/estimate/{id}` | Retrieve a quote/estimate by ID |
| create_estimate | POST | `/estimate` | Create a new estimate. Required: CustomerRef, Line items |
| get_report | GET | `/reports/{reportName}` | Run a financial report (ProfitAndLoss, BalanceSheet, etc.) |
| cdc | GET | `/cdc?entities={list}&changedSince={datetime}` | Change Data Capture — get all entities changed since a timestamp |

---

## Rate Limits and Restrictions

- **Rate limit:** 500 requests per minute per company (realm ID)
- **Concurrent requests:** 10 per second per realm + app combination
- **Batch endpoint:** 120 requests per minute per realm ID (tightened Oct 2025)
- **Report endpoints:** 200 requests per minute (resource-intensive)
- **Report cell cap:** 400,000 cells per response — queries exceeding this silently truncate
- **Retry strategy:** Exponential backoff with jitter on HTTP 429 responses. Do not retry immediately.
- **Versioning:** Always include `?minorversion=75` (or latest) on all requests. Omitting it defaults to the legacy 2014 schema. Minor versions 1–74 were phased out August 2025.
- **Pagination:** Offset-based using SQL-like `STARTPOSITION` and `MAXRESULTS` (max 1000). Not cursor-based. Order by `MetaData.LastUpdatedTime` to avoid missed/duplicate records during pagination.
- **SyncToken:** All update operations require the current `SyncToken` from the entity (optimistic concurrency). Stale SyncTokens cause 400 errors.
- **Pricing (2025+):** Writes (Core API) are free and unlimited. Reads (CorePlus API) are free up to 500,000/month on Builder Tier, then blocked. Paid tiers (Silver/Gold/Platinum) offer higher limits.

---

## Response Format Notes

All API responses are JSON. Entity responses wrap the object in a property matching its type:

```json
{
  "Invoice": {
    "Id": "130",
    "SyncToken": "0",
    "MetaData": {
      "CreateTime": "2026-04-01T10:00:00-07:00",
      "LastUpdatedTime": "2026-04-01T10:00:00-07:00"
    },
    "DocNumber": "1001",
    "TxnDate": "2026-04-01",
    "CustomerRef": {
      "value": "123",
      "name": "Acme Corp"
    },
    "Line": [
      {
        "Amount": 500.00,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": {"value": "45", "name": "Consulting"},
          "Qty": 5,
          "UnitPrice": 100
        }
      }
    ],
    "TotalAmt": 500.00,
    "Balance": 500.00,
    "EmailStatus": "NotSet",
    "PrintStatus": "NeedToPrint"
  }
}
```

**Query responses** wrap results in `QueryResponse`:

```json
{
  "QueryResponse": {
    "Customer": [
      {"Id": "1", "DisplayName": "Acme Corp", "Balance": 1500.00, "SyncToken": "3"},
      {"Id": "2", "DisplayName": "Beta Inc", "Balance": 0, "SyncToken": "1"}
    ],
    "startPosition": 1,
    "maxResults": 2,
    "totalCount": 2
  }
}
```

**Common patterns:**
- All entities have `Id`, `SyncToken`, and `MetaData` (CreateTime, LastUpdatedTime)
- References to other entities use `{EntityName}Ref` objects with `value` (ID) and optionally `name`
- Line items use a `DetailType` field to determine which detail object contains the data
- Errors return `{ "Fault": { "Error": [{ "Message": "...", "Detail": "...", "code": "..." }], "type": "..." } }`

---

## Token / Credential Notes

- Access tokens expire after exactly **60 minutes**. The token response includes `expires_in: 3600`.
- Refresh tokens rotate every **24–26 hours** — always store the latest refresh token returned.
- Refresh tokens have a **maximum validity of 5 years** (changed Nov 2025; previously 100-day rolling).
- If you attempt to refresh with an already-rotated refresh token, the entire auth chain is revoked and the user must manually re-authorize.
- Use a distributed lock/mutex around token refresh logic to prevent TOCTOU race conditions when multiple processes refresh simultaneously.
- The `realmId` (company ID) is returned during the OAuth flow and must be stored — it's required in every API URL.
- Sandbox and production use different base URLs and different credential sets (Development vs Production keys in the Intuit portal).
- A "Reconnect URL" is mandatory in the developer portal (as of Jan 2026) — users will be directed there when re-auth is needed.

---

## Additional References

- Official API docs: https://developer.intuit.com/app/developer/qbo/docs/develop
- API entity reference: https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account
- OAuth 2.0 playground: https://developer.intuit.com/app/developer/playground
- Intuit Developer Portal: https://developer.intuit.com
- New API docs (GitHub Pages): https://intuitdeveloper.github.io/intuit-api/docs/getting-started/authentication/
- QuickBooks V3 PHP SDK (good reference for entity shapes): https://intuit.github.io/QuickBooks-V3-PHP-SDK/
- Integration guide (comprehensive 2026): https://truto.one/blog/how-to-integrate-with-the-quickbooks-online-api-2026-guide
- Intuit App Partner Program (pricing): announced July 2025, tiered CorePlus pricing

---

## Notes for README

- Provides full access to QuickBooks Online accounting data: invoices, customers, vendors, bills, payments, accounts, items, estimates, and reports
- Uses OAuth 2.0 Authorization Code Flow — requires registering an app at developer.intuit.com
- All requests scoped to a company via `realmId` obtained during OAuth authorization
- Implements the QBO SQL-like query language for flexible entity reads (SELECT * FROM Customer WHERE ...)
- Supports Change Data Capture (CDC) for efficient incremental sync of modified entities
- Always pins API calls to `minorversion=75` to ensure latest schema (versions 1–74 deprecated)
- Handles 60-minute access token expiry with automatic refresh and token rotation
- Respects rate limits: 500 req/min per company, 10 concurrent, exponential backoff on 429
- Implements SyncToken-based optimistic concurrency for all update operations
- Supports both sandbox and production environments via configurable base URL
- Compatible with Claude, Cursor, and other MCP-enabled AI tools
