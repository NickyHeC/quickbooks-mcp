"""QuickBooks Online MCP tools.

All 20 tools from PROJECT.md: entity CRUD, SQL-like queries, financial reports,
and Change Data Capture. Requests go through DAuth via ctx.dispatch().
"""

import json
from typing import Any
from urllib.parse import quote

from dedalus_mcp import tool, get_context, HttpMethod, HttpRequest
from pydantic import BaseModel

from src.config import qbo_connection, MINOR_VERSION, realm_id


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class QBOResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Request helper
# ---------------------------------------------------------------------------


def _versioned(path: str) -> str:
    """Append minorversion query param to every request path."""
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}minorversion={MINOR_VERSION}"


async def api_request(
    method: HttpMethod,
    path: str,
    body: dict | None = None,
) -> dict:
    """Dispatch an authenticated request to QuickBooks through DAuth."""
    ctx = get_context()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = HttpRequest(
        method=method,
        path=_versioned(path),
        body=body,
        headers=headers,
    )
    resp = await ctx.dispatch(qbo_connection, req)
    if resp.success and resp.response is not None:
        resp_body = resp.response.body
        if isinstance(resp_body, dict):
            fault = resp_body.get("Fault")
            if fault:
                errors = fault.get("Error", [])
                msg = errors[0].get("Detail", errors[0].get("Message", "QBO API error")) if errors else "QBO API error"
                return {"success": False, "error": str(msg)}
        return {"success": True, "data": resp_body}
    error = resp.error.message if resp.error else "Request failed"
    return {"success": False, "error": error}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@tool(description="Run a SQL-like query against any QuickBooks entity (e.g. SELECT * FROM Customer WHERE Balance > 0). Supports STARTPOSITION and MAXRESULTS for pagination.")
async def query_entities(
    query: str,
    max_results: int = 100,
    start_position: int = 1,
) -> QBOResult:
    """Execute a QBO query-language statement.

    Args:
        query: A SQL-like query string (e.g. "SELECT * FROM Invoice WHERE TotalAmt > 1000").
        max_results: Maximum rows to return (1-1000, default 100).
        start_position: 1-based offset for pagination (default 1).

    """
    full_query = query.rstrip()
    if "MAXRESULTS" not in full_query.upper():
        full_query += f" MAXRESULTS {max_results}"
    if "STARTPOSITION" not in full_query.upper():
        full_query += f" STARTPOSITION {start_position}"
    result = await api_request(HttpMethod.GET, f"/query?query={quote(full_query)}")
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


@tool(description="Get company information including name, address, fiscal year, and settings.")
async def get_company_info() -> QBOResult:
    """Retrieve the company profile for the connected QuickBooks realm."""
    result = await api_request(HttpMethod.GET, f"/companyinfo/{realm_id}")
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@tool(description="Get a customer by ID.")
async def get_customer(customer_id: str) -> QBOResult:
    """Retrieve a single customer record.

    Args:
        customer_id: The QuickBooks customer ID.

    """
    result = await api_request(HttpMethod.GET, f"/customer/{customer_id}")
    return QBOResult(**result)


@tool(description="Create a new customer. DisplayName is required; other fields are optional.")
async def create_customer(
    display_name: str,
    given_name: str = "",
    family_name: str = "",
    email: str = "",
    phone: str = "",
    company_name: str = "",
) -> QBOResult:
    """Create a customer in QuickBooks.

    Args:
        display_name: Required display name for the customer.
        given_name: Customer's first name.
        family_name: Customer's last name.
        email: Primary email address.
        phone: Primary phone number.
        company_name: Company name.

    """
    body: dict[str, Any] = {"DisplayName": display_name}
    if given_name:
        body["GivenName"] = given_name
    if family_name:
        body["FamilyName"] = family_name
    if email:
        body["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        body["PrimaryPhone"] = {"FreeFormNumber": phone}
    if company_name:
        body["CompanyName"] = company_name
    result = await api_request(HttpMethod.POST, "/customer", body)
    return QBOResult(**result)


@tool(description="Update an existing customer. Requires the customer ID and current SyncToken. Pass updated fields as a JSON object string.")
async def update_customer(
    customer_id: str,
    sync_token: str,
    updates_json: str,
) -> QBOResult:
    """Update a customer record.

    The updates_json should be a JSON object with QuickBooks field names, e.g.:
    {"DisplayName": "New Name", "PrimaryEmailAddr": {"Address": "new@example.com"}}

    Args:
        customer_id: The customer's QuickBooks ID.
        sync_token: Current SyncToken from the customer record (for optimistic concurrency).
        updates_json: JSON object string of fields to update.

    """
    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError as e:
        return QBOResult(success=False, error=f"Invalid JSON in updates_json: {e}")
    body = {"Id": customer_id, "SyncToken": sync_token, **updates}
    result = await api_request(HttpMethod.POST, "/customer", body)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


@tool(description="Get an invoice by ID.")
async def get_invoice(invoice_id: str) -> QBOResult:
    """Retrieve a single invoice.

    Args:
        invoice_id: The QuickBooks invoice ID.

    """
    result = await api_request(HttpMethod.GET, f"/invoice/{invoice_id}")
    return QBOResult(**result)


@tool(description="Create a new invoice. Requires a customer ID and line items as a JSON array string.")
async def create_invoice(
    customer_id: str,
    lines_json: str,
    txn_date: str = "",
    due_date: str = "",
    doc_number: str = "",
) -> QBOResult:
    """Create an invoice in QuickBooks.

    lines_json must be a JSON array of line item objects, e.g.:
    [{"Amount": 500, "DetailType": "SalesItemLineDetail",
      "SalesItemLineDetail": {"ItemRef": {"value": "1"}, "Qty": 5, "UnitPrice": 100}}]

    Args:
        customer_id: The customer to invoice.
        lines_json: JSON array string of Line objects.
        txn_date: Transaction date (YYYY-MM-DD). Defaults to today.
        due_date: Due date (YYYY-MM-DD). Defaults to terms.
        doc_number: Optional invoice number.

    """
    try:
        lines = json.loads(lines_json)
    except json.JSONDecodeError as e:
        return QBOResult(success=False, error=f"Invalid JSON in lines_json: {e}")
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "Line": lines,
    }
    if txn_date:
        body["TxnDate"] = txn_date
    if due_date:
        body["DueDate"] = due_date
    if doc_number:
        body["DocNumber"] = doc_number
    result = await api_request(HttpMethod.POST, "/invoice", body)
    return QBOResult(**result)


@tool(description="Email an invoice to the customer. Optionally override the recipient email.")
async def send_invoice(invoice_id: str, email: str = "") -> QBOResult:
    """Send (email) an invoice.

    Args:
        invoice_id: The invoice ID to send.
        email: Override recipient email. If empty, uses the customer's email on file.

    """
    path = f"/invoice/{invoice_id}/send"
    if email:
        path += f"?sendTo={quote(email)}"
    result = await api_request(HttpMethod.POST, path)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


@tool(description="Get a vendor by ID.")
async def get_vendor(vendor_id: str) -> QBOResult:
    """Retrieve a single vendor record.

    Args:
        vendor_id: The QuickBooks vendor ID.

    """
    result = await api_request(HttpMethod.GET, f"/vendor/{vendor_id}")
    return QBOResult(**result)


@tool(description="Create a new vendor. DisplayName is required.")
async def create_vendor(
    display_name: str,
    given_name: str = "",
    family_name: str = "",
    email: str = "",
    phone: str = "",
    company_name: str = "",
) -> QBOResult:
    """Create a vendor in QuickBooks.

    Args:
        display_name: Required display name for the vendor.
        given_name: Vendor's first name.
        family_name: Vendor's last name.
        email: Primary email address.
        phone: Primary phone number.
        company_name: Company name.

    """
    body: dict[str, Any] = {"DisplayName": display_name}
    if given_name:
        body["GivenName"] = given_name
    if family_name:
        body["FamilyName"] = family_name
    if email:
        body["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        body["PrimaryPhone"] = {"FreeFormNumber": phone}
    if company_name:
        body["CompanyName"] = company_name
    result = await api_request(HttpMethod.POST, "/vendor", body)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------


@tool(description="Get a bill by ID.")
async def get_bill(bill_id: str) -> QBOResult:
    """Retrieve a single bill.

    Args:
        bill_id: The QuickBooks bill ID.

    """
    result = await api_request(HttpMethod.GET, f"/bill/{bill_id}")
    return QBOResult(**result)


@tool(description="Create a new bill. Requires a vendor ID and line items as a JSON array string.")
async def create_bill(
    vendor_id: str,
    lines_json: str,
    txn_date: str = "",
    due_date: str = "",
) -> QBOResult:
    """Create a bill in QuickBooks.

    lines_json must be a JSON array of line item objects, e.g.:
    [{"Amount": 200, "DetailType": "AccountBasedExpenseLineDetail",
      "AccountBasedExpenseLineDetail": {"AccountRef": {"value": "7"}}}]

    Args:
        vendor_id: The vendor this bill is from.
        lines_json: JSON array string of Line objects.
        txn_date: Transaction date (YYYY-MM-DD).
        due_date: Due date (YYYY-MM-DD).

    """
    try:
        lines = json.loads(lines_json)
    except json.JSONDecodeError as e:
        return QBOResult(success=False, error=f"Invalid JSON in lines_json: {e}")
    body: dict[str, Any] = {
        "VendorRef": {"value": vendor_id},
        "Line": lines,
    }
    if txn_date:
        body["TxnDate"] = txn_date
    if due_date:
        body["DueDate"] = due_date
    result = await api_request(HttpMethod.POST, "/bill", body)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@tool(description="Get a payment by ID.")
async def get_payment(payment_id: str) -> QBOResult:
    """Retrieve a single payment record.

    Args:
        payment_id: The QuickBooks payment ID.

    """
    result = await api_request(HttpMethod.GET, f"/payment/{payment_id}")
    return QBOResult(**result)


@tool(description="Record a customer payment. Requires customer ID and total amount.")
async def create_payment(
    customer_id: str,
    total_amount: float,
    payment_method_id: str = "",
    txn_date: str = "",
) -> QBOResult:
    """Create a payment in QuickBooks.

    Args:
        customer_id: The customer making the payment.
        total_amount: Payment amount.
        payment_method_id: Optional payment method reference ID.
        txn_date: Transaction date (YYYY-MM-DD).

    """
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "TotalAmt": total_amount,
    }
    if payment_method_id:
        body["PaymentMethodRef"] = {"value": payment_method_id}
    if txn_date:
        body["TxnDate"] = txn_date
    result = await api_request(HttpMethod.POST, "/payment", body)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@tool(description="Get a chart-of-accounts entry by ID.")
async def get_account(account_id: str) -> QBOResult:
    """Retrieve a single account from the chart of accounts.

    Args:
        account_id: The QuickBooks account ID.

    """
    result = await api_request(HttpMethod.GET, f"/account/{account_id}")
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@tool(description="Get a product or service item by ID.")
async def get_item(item_id: str) -> QBOResult:
    """Retrieve a single product/service item.

    Args:
        item_id: The QuickBooks item ID.

    """
    result = await api_request(HttpMethod.GET, f"/item/{item_id}")
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------


@tool(description="Get an estimate (quote) by ID.")
async def get_estimate(estimate_id: str) -> QBOResult:
    """Retrieve a single estimate.

    Args:
        estimate_id: The QuickBooks estimate ID.

    """
    result = await api_request(HttpMethod.GET, f"/estimate/{estimate_id}")
    return QBOResult(**result)


@tool(description="Create a new estimate. Requires a customer ID and line items as a JSON array string.")
async def create_estimate(
    customer_id: str,
    lines_json: str,
    txn_date: str = "",
    expiration_date: str = "",
) -> QBOResult:
    """Create an estimate (quote) in QuickBooks.

    lines_json must be a JSON array of line item objects, e.g.:
    [{"Amount": 300, "DetailType": "SalesItemLineDetail",
      "SalesItemLineDetail": {"ItemRef": {"value": "1"}, "Qty": 3, "UnitPrice": 100}}]

    Args:
        customer_id: The customer this estimate is for.
        lines_json: JSON array string of Line objects.
        txn_date: Transaction date (YYYY-MM-DD).
        expiration_date: Expiration date (YYYY-MM-DD).

    """
    try:
        lines = json.loads(lines_json)
    except json.JSONDecodeError as e:
        return QBOResult(success=False, error=f"Invalid JSON in lines_json: {e}")
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "Line": lines,
    }
    if txn_date:
        body["TxnDate"] = txn_date
    if expiration_date:
        body["ExpirationDate"] = expiration_date
    result = await api_request(HttpMethod.POST, "/estimate", body)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@tool(description="Run a financial report (ProfitAndLoss, BalanceSheet, CashFlow, etc.). Supports date range filtering.")
async def get_report(
    report_name: str,
    start_date: str = "",
    end_date: str = "",
    accounting_method: str = "",
    summarize_column_by: str = "",
) -> QBOResult:
    """Run a QuickBooks financial report.

    Args:
        report_name: Report type — ProfitAndLoss, BalanceSheet, CashFlow, GeneralLedger,
                     TrialBalance, AgedReceivables, AgedPayables, CustomerIncome, etc.
        start_date: Report start date (YYYY-MM-DD).
        end_date: Report end date (YYYY-MM-DD).
        accounting_method: "Cash" or "Accrual".
        summarize_column_by: Group columns by "Month", "Quarter", "Year", etc.

    """
    params: list[str] = []
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")
    if accounting_method:
        params.append(f"accounting_method={accounting_method}")
    if summarize_column_by:
        params.append(f"summarize_column_by={summarize_column_by}")
    query_string = "&".join(params)
    path = f"/reports/{report_name}"
    if query_string:
        path += f"?{query_string}"
    result = await api_request(HttpMethod.GET, path)
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Change Data Capture
# ---------------------------------------------------------------------------


@tool(description="Get all entities changed since a timestamp (Change Data Capture). Useful for incremental sync.")
async def cdc(
    entities: str,
    changed_since: str,
) -> QBOResult:
    """Fetch entities modified after a given timestamp.

    Args:
        entities: Comma-separated entity names (e.g. "Customer,Invoice,Payment").
        changed_since: ISO 8601 datetime (e.g. "2026-04-01T00:00:00-07:00").

    """
    result = await api_request(
        HttpMethod.GET,
        f"/cdc?entities={quote(entities)}&changedSince={quote(changed_since)}",
    )
    return QBOResult(**result)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

tools = [
    query_entities,
    get_company_info,
    get_customer,
    create_customer,
    update_customer,
    get_invoice,
    create_invoice,
    send_invoice,
    get_vendor,
    create_vendor,
    get_bill,
    create_bill,
    get_payment,
    create_payment,
    get_account,
    get_item,
    get_estimate,
    create_estimate,
    get_report,
    cdc,
]
