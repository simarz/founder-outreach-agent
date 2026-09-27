"""Quick read-only view of everyone you've tracked, without scanning Gmail.

    python status.py
"""
from datetime import datetime, timezone

import database
import tracker


def main():
    database.init_db()
    rows = database.all_threads()
    if not rows:
        print("No tracked threads yet. Run `python main.py` first.")
        return

    now = datetime.now(timezone.utc)
    # Friendly labels for the stored status (falls back gracefully on old rows).
    labels = {
        "due": "FOLLOW UP (new outreach)",
        "waiting": "waiting",
        "closed_no_reply": "closed (no reply)",
        "replied_due": "FOLLOW UP (replied)",
        "replied_waiting": "in conversation",
        # legacy rows from earlier versions
        "replied": "replied",
        "responded": "responded",
    }
    print(f"{'COMPANY':<20}{'EMAIL':<32}{'SENT':<12}{'F/U':<5}{'STATUS'}")
    print("-" * 95)
    for r in rows:
        try:
            last_sent = datetime.fromisoformat(r["last_sent_date"])
            days = tracker.calendar_days_since(now, last_sent)
            sent_str = tracker.local_date(last_sent).isoformat()
        except Exception:
            days, sent_str = "?", "?"
        keys = r.keys()
        stored = r["status"] if "status" in keys else None
        if stored:
            status = labels.get(stored, stored)
            if stored in ("due", "waiting", "replied_due", "replied_waiting"):
                status = f"{status} ({days}d)"
        else:  # pre-migration fallback
            status = "replied" if r["replied"] else f"waiting ({days}d)"
        fu = r["followups_sent"] if "followups_sent" in keys and r["followups_sent"] is not None else 0
        company = (r["company"] or "")[:18]
        print(f"{company:<20}{r['recipient_email']:<32}{sent_str:<12}{fu:<5}{status}")


if __name__ == "__main__":
    main()
