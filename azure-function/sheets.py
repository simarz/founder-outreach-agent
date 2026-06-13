"""Mirror the tracking table into a Google Sheet.

Each run clears the tab and rewrites it from the current data, so the sheet is
always an exact snapshot of the agent's latest state. Best-effort by design: the
caller wraps this in try/except so a Sheets problem never fails the whole run.
"""
from datetime import datetime, timezone

HEADER = [
    "Name", "Company", "Email", "Subject", "First sent", "Last sent",
    "Follow-ups sent", "Status", "Replied date", "Last updated",
]

# Human-friendly status labels for the sheet.
STATUS_LABELS = {
    "replied": "Replied",
    "due": "Follow up now",
    "waiting": "Waiting",
    "closed_no_reply": "Closed — no reply",
}


def build_rows(records):
    """Turn tracking records (list of dicts) into rows for the sheet.

    Each record needs: name, company, email, subject, first_sent, last_sent,
    followups_sent, status, replied_date (any may be missing/None).
    """
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    for r in records:
        rows.append([
            r.get("name") or "",
            r.get("company") or "",
            r.get("email") or "",
            (r.get("subject") or "")[:120],
            (r.get("first_sent") or "")[:10],
            (r.get("last_sent") or "")[:10],
            r.get("followups_sent", 0),
            STATUS_LABELS.get(r.get("status"), r.get("status") or ""),
            (r.get("replied_date") or "")[:10],
            updated,
        ])
    # Sort: action-needed first, then waiting, replied, closed.
    order = {"Follow up now": 0, "Waiting": 1, "Replied": 2, "Closed — no reply": 3}
    rows.sort(key=lambda x: (order.get(x[7], 9), x[1].lower()))
    return rows


def update_sheet(sheets_service, spreadsheet_id, records, tab="Sheet1"):
    """Clear the tab and write the header + all records. Returns the row count."""
    rows = build_rows(records)
    values = [HEADER] + rows

    api = sheets_service.spreadsheets().values()
    # Clear a generous range so stale rows from a previous (larger) run are removed.
    api.clear(spreadsheetId=spreadsheet_id, range=f"{tab}!A1:Z10000").execute()
    api.update(
        spreadsheetId=spreadsheet_id,
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    return len(rows)
