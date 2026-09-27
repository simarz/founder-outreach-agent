"""Mirror the tracking table into a Google Sheet.

Each run clears the tab and rewrites it from the current data, so the sheet is
always an exact snapshot of the agent's latest state. Best-effort by design: the
caller wraps this in try/except so a Sheets problem never fails the whole run.
"""
from datetime import datetime

from tracker import LOCAL_TZ

HEADER = [
    "Company", "Email", "Subject", "First sent", "Last sent",
    "Follow-ups sent", "Status", "Replied date", "Last updated",
]

# Human-friendly status labels for the sheet.
STATUS_LABELS = {
    "due": "Follow up now",
    "waiting": "Waiting",
    "closed_no_reply": "Closed — no reply",
    "replied_due": "Follow up now",
    "replied_waiting": "In conversation",
    # Legacy values from earlier versions, kept so old rows still render.
    "replied": "Replied",
    "responded": "Responded",
}


def _is_replied(status):
    """Thread belongs to the Replied category (founder has engaged)."""
    return (status or "").startswith("replied_") or status in ("replied", "responded")


def build_rows(records):
    """Turn tracking records (list of dicts) into rows for the sheet.

    Each record needs: name, company, email, subject, first_sent, last_sent,
    followups_sent, status, replied_date (any may be missing/None).
    """
    updated = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")
    rows = []
    for r in records:
        rows.append([
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
    # Sort: action-needed first, then in-flight, closed last.
    order = {
        "Follow up now": 0, "In conversation": 1, "Waiting": 1,
        "Replied": 2, "Responded": 2, "Closed — no reply": 3,
    }
    rows.sort(key=lambda x: (order.get(x[6], 9), x[0].lower()))
    return rows


def _ensure_tab(sheets_service, spreadsheet_id, title):
    """Create the tab if missing; return the spreadsheet's tab titles."""
    meta = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties.title"
    ).execute()
    titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if title not in titles:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
        titles.add(title)
    return titles


def update_sheet(sheets_service, spreadsheet_id, records,
                 tab="Sheet1", replied_tab="Replied"):
    """Write records across two tabs and return (outreach_count, replied_count).

    Main tab : outreach with no engagement yet (waiting / due / closed-no-reply)
    Replied  : founders who engaged — an in-thread reply was detected, or you
               tagged the thread with the responded label. Still on the 7-day
               follow-up cadence.
    """
    outreach = [r for r in records if not _is_replied(r.get("status"))]
    replied = [r for r in records if _is_replied(r.get("status"))]

    titles = _ensure_tab(sheets_service, spreadsheet_id, replied_tab)
    api = sheets_service.spreadsheets().values()
    for tab_name, recs in ((tab, outreach), (replied_tab, replied)):
        # Clear a generous range so stale rows from a previous (larger) run go away.
        api.clear(spreadsheetId=spreadsheet_id, range=f"{tab_name}!A1:Z10000").execute()
        api.update(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="RAW",
            body={"values": [HEADER] + build_rows(recs)},
        ).execute()

    # Clear the legacy "Responded" tab from the earlier design so it doesn't
    # linger with stale data alongside the new Replied tab.
    if "Responded" in titles and replied_tab != "Responded":
        api.clear(spreadsheetId=spreadsheet_id, range="Responded!A1:Z10000").execute()

    return len(outreach), len(replied)
