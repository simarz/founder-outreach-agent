"""Quick read-only view of everyone you've tracked, without scanning Gmail.

    python status.py
"""
from datetime import datetime, timezone

import database


def main():
    database.init_db()
    rows = database.all_threads()
    if not rows:
        print("No tracked threads yet. Run `python main.py` first.")
        return

    now = datetime.now(timezone.utc)
    # Friendly labels for the stored status (falls back gracefully on old rows).
    labels = {
        "replied": "replied",
        "due": "FOLLOW UP",
        "waiting": "waiting",
        "closed_no_reply": "closed (no reply)",
    }
    print(f"{'COMPANY':<20}{'EMAIL':<32}{'SENT':<12}{'F/U':<5}{'STATUS'}")
    print("-" * 95)
    for r in rows:
        try:
            last_sent = datetime.fromisoformat(r["last_sent_date"])
            days = (now - last_sent).days
            sent_str = last_sent.strftime("%Y-%m-%d")
        except Exception:
            days, sent_str = "?", "?"
        keys = r.keys()
        stored = r["status"] if "status" in keys else None
        if stored:
            status = labels.get(stored, stored)
            if stored in ("due", "waiting"):
                status = f"{status} ({days}d)"
        else:  # pre-migration fallback
            status = "replied" if r["replied"] else f"waiting ({days}d)"
        fu = r["followups_sent"] if "followups_sent" in keys and r["followups_sent"] is not None else 0
        company = (r["company"] or "")[:18]
        print(f"{company:<20}{r['recipient_email']:<32}{sent_str:<12}{fu:<5}{status}")


if __name__ == "__main__":
    main()
