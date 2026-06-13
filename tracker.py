"""Core Gmail scanning logic.

For each thread carrying the tracking label we work out:
  - who you emailed (recipient of your first message in the thread)
  - when you last messaged them
  - whether they have replied since your last message

Follow-up status is intentionally derived from "your last message" so that if
you DO follow up, the 7-day clock resets automatically.
"""
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime

# Personal-email providers we never treat as a "company".
GENERIC_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "yahoo.co.uk", "icloud.com", "proton.me", "protonmail.com", "aol.com",
    "live.com", "me.com", "msn.com", "gmx.com",
}


def _header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def guess_company(email):
    """Rough company name from the email domain (acme.com -> 'Acme')."""
    domain = email.split("@")[-1].lower().strip()
    if not domain or domain in GENERIC_DOMAINS:
        return ""
    parts = domain.split(".")
    root = parts[-2] if len(parts) >= 2 else parts[0]
    return root.capitalize()


def find_label_id(service, label_name):
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for l in labels:
        if l.get("name", "").lower() == label_name.lower():
            return l["id"]
    return None


def list_labeled_thread_ids(service, label_name):
    """Thread IDs carrying the label, or None if the label doesn't exist."""
    label_id = find_label_id(service, label_name)
    if not label_id:
        return None
    thread_ids = []
    page_token = None
    while True:
        resp = service.users().threads().list(
            userId="me", labelIds=[label_id], maxResults=100, pageToken=page_token
        ).execute()
        thread_ids.extend(t["id"] for t in resp.get("threads", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return thread_ids


def _message_datetime(message, headers):
    date_raw = _header(headers, "Date")
    try:
        dt = parsedate_to_datetime(date_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        # Fall back to Gmail's internalDate (epoch milliseconds).
        return datetime.fromtimestamp(
            int(message.get("internalDate", 0)) / 1000, tz=timezone.utc
        )


def analyze_thread(service, thread_id, my_email):
    """Return tracking info for a single thread."""
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="metadata",
        metadataHeaders=["From", "To", "Date", "Subject"],
    ).execute()

    my_email = my_email.lower()
    parsed = []
    for m in thread.get("messages", []):
        headers = m.get("payload", {}).get("headers", [])
        from_name, from_addr = parseaddr(_header(headers, "From"))
        to_name, to_addr = parseaddr(_header(headers, "To"))
        parsed.append({
            "is_me": my_email in (from_addr or "").lower(),
            "to_addr": (to_addr or "").lower(),
            "to_name": to_name or "",
            "subject": _header(headers, "Subject"),
            "date": _message_datetime(m, headers),
        })
    parsed.sort(key=lambda p: p["date"])

    my_messages = [p for p in parsed if p["is_me"]]
    other_dates = [p["date"] for p in parsed if not p["is_me"]]

    if not my_messages:
        # Labeled an inbound-only thread; nothing to follow up on.
        return {"last_sent": None, "recipient_email": ""}

    first = my_messages[0]
    last_sent = max(p["date"] for p in my_messages)
    replies_after = [d for d in other_dates if d > last_sent]
    replied = bool(replies_after)

    return {
        "thread_id": thread_id,
        "recipient_email": first["to_addr"],
        "recipient_name": first["to_name"],
        "subject": first["subject"],
        "first_sent": my_messages[0]["date"],
        "last_sent": last_sent,
        "replied": replied,
        "replied_date": min(replies_after) if replies_after else None,
        # How many emails YOU sent in this thread. 1 = initial outreach only,
        # 2 = one follow-up sent, 3 = two follow-ups sent, etc.
        "my_message_count": len(my_messages),
    }


def classify_thread(info, now, followup_days, max_followups):
    """Decide a thread's follow-up status.

    Returns (status, days_since_last_sent, followups_sent) where status is one of:
      - "replied"          : the founder responded; nothing to do
      - "due"              : no reply, 7+ days, and we can still follow up
      - "closed_no_reply"  : no reply after the allowed number of follow-ups; stop
      - "waiting"          : no reply yet, but the follow-up window hasn't elapsed
    """
    days = (now - info["last_sent"]).days
    followups_sent = max(info.get("my_message_count", 1) - 1, 0)
    if info["replied"]:
        status = "replied"
    elif followups_sent >= max_followups:
        status = "closed_no_reply"
    elif days >= followup_days:
        status = "due"
    else:
        status = "waiting"
    return status, days, followups_sent
