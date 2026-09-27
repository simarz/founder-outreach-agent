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
from zoneinfo import ZoneInfo

# Calendar days are counted in this timezone, ignoring time of day.
LOCAL_TZ = ZoneInfo("America/New_York")


def local_date(dt):
    """The Eastern-time calendar date of a timezone-aware datetime."""
    return dt.astimezone(LOCAL_TZ).date()


def calendar_days_since(now, then):
    """Count calendar days, not 24-hour periods: a message sent Monday at 5pm
    is 7 days old the following Monday, whatever time the check runs."""
    return (local_date(now) - local_date(then)).days

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


def find_label_id(service, label_name, match_nested=False):
    """Find a label ID by name.

    With match_nested=True a nested label also matches by its leaf name —
    e.g. 'responded' matches 'founders/responded' (Gmail names nested labels
    parent/child).
    """
    target = label_name.lower()
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for l in labels:
        name = l.get("name", "").lower()
        if name == target or (match_nested and name.endswith("/" + target)):
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


def analyze_thread(service, thread_id, my_email, responded_label_id=None):
    """Return tracking info for a single thread.

    If responded_label_id is given, also reports whether any message in the
    thread carries that label — the manual "this founder responded" marker for
    replies that happen outside the thread (new email, LinkedIn, a call).
    """
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="metadata",
        metadataHeaders=["From", "To", "Date", "Subject"],
    ).execute()

    my_email = my_email.lower()
    parsed = []
    label_ids = set()
    for m in thread.get("messages", []):
        label_ids.update(m.get("labelIds", []))
        # Unsent drafts are part of the thread but must not reset the clock.
        if "DRAFT" in m.get("labelIds", []):
            continue
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
    their_last = max(other_dates) if other_dates else None
    # Messages you sent AFTER their most recent reply = nudges in the current
    # round of the conversation. 0 when they've never written in-thread.
    my_after_their_last = (
        len([p for p in my_messages if p["date"] > their_last]) if their_last else 0
    )

    return {
        "thread_id": thread_id,
        "recipient_email": first["to_addr"],
        "recipient_name": first["to_name"],
        "subject": first["subject"],
        "first_sent": my_messages[0]["date"],
        "last_sent": last_sent,
        "replied": bool(replies_after),
        "replied_date": min(replies_after) if replies_after else None,
        # Founder has EVER written in this thread (survives you replying back).
        "ever_replied": bool(other_dates),
        "their_last_date": their_last,
        "last_message_date": parsed[-1]["date"],
        "my_msgs_after_their_last": my_after_their_last,
        # How many emails YOU sent in this thread. 1 = initial outreach only,
        # 2 = one follow-up sent, 3 = two follow-ups sent, etc.
        "my_message_count": len(my_messages),
        # True if you manually tagged this thread with the responded label.
        "manually_responded": bool(responded_label_id) and responded_label_id in label_ids,
    }


def classify_thread(info, now, followup_days, max_followups):
    """Decide a thread's follow-up status.

    Returns (status, days, followups_sent).

    Replied category — the founder has engaged (an in-thread reply was seen, or
    you tagged the thread with the responded label). These stay on the same
    7-day cadence but are never closed out by the follow-up cap:
      - "replied_due"     : conversation quiet for followup_days+; follow up
      - "replied_waiting" : conversation active within the window
      (days = staleness of the LAST message in the thread, either party;
       followups_sent = your messages since their most recent reply)

    Outreach category — no engagement yet:
      - "due"             : no reply, followup_days+ since your last email
      - "waiting"         : no reply yet, window hasn't elapsed
      - "closed_no_reply" : no reply after max_followups follow-ups; stop
    """
    if info.get("manually_responded") or info.get("ever_replied"):
        days = calendar_days_since(now, info["last_message_date"])
        followups_sent = info.get("my_msgs_after_their_last", 0)
        status = "replied_due" if days >= followup_days else "replied_waiting"
        return status, days, followups_sent

    days = calendar_days_since(now, info["last_sent"])
    followups_sent = max(info.get("my_message_count", 1) - 1, 0)
    if followups_sent >= max_followups:
        status = "closed_no_reply"
    elif days >= followup_days:
        status = "due"
    else:
        status = "waiting"
    return status, days, followups_sent
