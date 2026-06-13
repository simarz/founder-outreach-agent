"""Founder Follow-up Agent — entry point.

Run daily (via the Windows scheduled task) or manually:

    python main.py

It scans labeled Gmail threads, updates the local tracking database and
contacts.csv, then emails you a digest of founders due for follow-up.
"""
import json
import os
from datetime import datetime, timezone

import contacts as contacts_mod
import database
import gmail_auth
import notifier
import sheets
import tracker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = load_config()
    label_name = cfg["label_name"]
    followup_days = int(cfg["followup_days"])
    max_followups = int(cfg.get("max_followups", 2))
    notify_email = cfg["notify_email"]
    sheet_id = (cfg.get("sheet_id") or "").strip()

    service = gmail_auth.get_service()
    my_email = service.users().getProfile(userId="me").execute()["emailAddress"]
    database.init_db()
    overrides = contacts_mod.load_contacts()

    thread_ids = tracker.list_labeled_thread_ids(service, label_name)
    if thread_ids is None:
        print(
            f"[!] Gmail label '{label_name}' not found.\n"
            f"    Create a label named '{label_name}' and apply it to the founder "
            f"outreach emails you want tracked, then run again."
        )
        return

    print(f"Scanning {len(thread_ids)} labeled thread(s) as {my_email} ...")
    now = datetime.now(timezone.utc)
    due_list = []
    closed_list = []
    sheet_records = []
    tracked_count = 0

    for tid in thread_ids:
        info = tracker.analyze_thread(service, tid, my_email)
        if not info.get("last_sent") or not info.get("recipient_email"):
            continue
        tracked_count += 1
        email = info["recipient_email"]

        # Hybrid name/company: your contacts.csv edits win; otherwise auto-fill.
        override = overrides.get(email)
        if override and (override["name"] or override["company"]):
            name = override["name"] or info["recipient_name"]
            company = override["company"] or tracker.guess_company(email)
        else:
            name = info["recipient_name"]
            company = tracker.guess_company(email)
        overrides[email] = {"name": name, "company": company}

        status, days, followups_sent = tracker.classify_thread(
            info, now, followup_days, max_followups
        )

        database.upsert_thread({
            "thread_id": info["thread_id"],
            "recipient_email": email,
            "recipient_name": name,
            "company": company,
            "subject": info["subject"],
            "first_sent_date": info["first_sent"].isoformat(),
            "last_sent_date": info["last_sent"].isoformat(),
            "replied": 1 if info["replied"] else 0,
            "replied_date": info["replied_date"].isoformat() if info["replied_date"] else None,
            "status": status,
            "followups_sent": followups_sent,
        })

        entry = {
            "name": name, "company": company, "email": email,
            "sent": info["last_sent"].strftime("%Y-%m-%d"),
            "days": days, "followups_sent": followups_sent, "thread_id": tid,
        }
        if status == "due":
            due_list.append(entry)
        elif status == "closed_no_reply" and not database.get_closed_notified(tid):
            # Only surface a newly-closed thread once.
            closed_list.append(entry)

        sheet_records.append({
            "name": name, "company": company, "email": email,
            "subject": info["subject"],
            "first_sent": info["first_sent"].isoformat(),
            "last_sent": info["last_sent"].isoformat(),
            "followups_sent": followups_sent, "status": status,
            "replied_date": info["replied_date"].isoformat() if info["replied_date"] else "",
        })

    contacts_mod.save_contacts(overrides)
    due_list.sort(key=lambda d: d["days"], reverse=True)

    print(f"Tracked {tracked_count} outreach thread(s). "
          f"{len(due_list)} due, {len(closed_list)} newly closed:")
    for d in due_list:
        who = d["name"] or d["email"]
        print(f"  - DUE: {who} ({d['company'] or 'n/a'}) — {d['days']} days, "
              f"{d['followups_sent']} follow-up(s) sent")
    for d in closed_list:
        who = d["name"] or d["email"]
        print(f"  - CLOSED: {who} ({d['company'] or 'n/a'}) — no reply after "
              f"{d['followups_sent']} follow-up(s)")

    if due_list or closed_list:
        if notifier.send_digest(service, notify_email, due_list, closed_list,
                                followup_days, max_followups):
            today = now.strftime("%Y-%m-%d")
            for d in due_list:
                database.mark_notified(d["thread_id"], today)
            for d in closed_list:
                database.mark_closed_notified(d["thread_id"])
            print(f"Digest emailed to {notify_email}.")
    else:
        print("Nothing due — no email sent.")

    # Mirror the full tracking table to Google Sheets (optional, best-effort).
    if sheet_id:
        try:
            n = sheets.update_sheet(
                gmail_auth.get_sheets_service(), sheet_id, sheet_records
            )
            print(f"Google Sheet updated ({n} row(s)).")
        except Exception as exc:  # never let a Sheets error fail the run
            print(f"[!] Google Sheet update skipped: {exc}")


if __name__ == "__main__":
    main()
