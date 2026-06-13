"""Azure Functions app — Founder Follow-up Agent.

Two triggers:
  - daily_followup : Timer trigger, runs on a cron schedule (default 8 AM).
  - run_now        : HTTP trigger, lets you fire a run on demand for testing.

Both call run_agent(), which scans labeled Gmail threads, updates Blob state,
and emails you a digest of founders due for follow-up.
"""
import logging
import os
from datetime import datetime, timezone

import azure.functions as func

import gmail_auth_cloud
import notifier
import sheets
import storage
import tracker

app = func.FunctionApp()


def run_agent():
    label_name = os.environ.get("LABEL_NAME", "founders")
    followup_days = int(os.environ.get("FOLLOWUP_DAYS", "7"))
    max_followups = int(os.environ.get("MAX_FOLLOWUPS", "2"))
    notify_email = os.environ["NOTIFY_EMAIL"]
    sheet_id = (os.environ.get("SHEET_ID") or "").strip()

    service = gmail_auth_cloud.get_service()
    my_email = service.users().getProfile(userId="me").execute()["emailAddress"]
    overrides = storage.load_contacts()
    history = storage.load_tracking()

    thread_ids = tracker.list_labeled_thread_ids(service, label_name)
    if thread_ids is None:
        msg = f"Gmail label '{label_name}' not found. Nothing scanned."
        logging.warning(msg)
        return msg

    now = datetime.now(timezone.utc)
    due_list = []
    closed_list = []
    sheet_records = []
    tracked = 0

    for tid in thread_ids:
        info = tracker.analyze_thread(service, tid, my_email)
        if not info.get("last_sent") or not info.get("recipient_email"):
            continue
        tracked += 1
        email = info["recipient_email"]

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

        # Preserve whether we've already sent the one-time 'closed' notice.
        prev_closed_notified = history.get(info["thread_id"], {}).get("closed_notified", False)
        history[info["thread_id"]] = {
            "recipient_email": email,
            "recipient_name": name,
            "company": company,
            "subject": info["subject"],
            "first_sent_date": info["first_sent"].isoformat(),
            "last_sent_date": info["last_sent"].isoformat(),
            "replied": bool(info["replied"]),
            "replied_date": info["replied_date"].isoformat() if info["replied_date"] else None,
            "status": status,
            "followups_sent": followups_sent,
            "closed_notified": prev_closed_notified,
        }

        entry = {
            "name": name, "company": company, "email": email,
            "sent": info["last_sent"].strftime("%Y-%m-%d"),
            "days": days, "followups_sent": followups_sent, "thread_id": tid,
        }
        if status == "due":
            due_list.append(entry)
        elif status == "closed_no_reply" and not prev_closed_notified:
            closed_list.append(entry)

        sheet_records.append({
            "name": name, "company": company, "email": email,
            "subject": info["subject"],
            "first_sent": info["first_sent"].isoformat(),
            "last_sent": info["last_sent"].isoformat(),
            "followups_sent": followups_sent, "status": status,
            "replied_date": info["replied_date"].isoformat() if info["replied_date"] else "",
        })

    due_list.sort(key=lambda d: d["days"], reverse=True)
    sent = False
    if due_list or closed_list:
        sent = notifier.send_digest(
            service, notify_email, due_list, closed_list, followup_days, max_followups
        )
        if sent:
            # Record that newly-closed threads have now been announced once.
            for d in closed_list:
                history[d["thread_id"]]["closed_notified"] = True

    storage.save_contacts(overrides)
    storage.save_tracking(history)

    # Mirror the full tracking table to Google Sheets (optional, best-effort).
    sheet_rows = 0
    if sheet_id:
        try:
            sheet_rows = sheets.update_sheet(
                gmail_auth_cloud.get_sheets_service(), sheet_id, sheet_records
            )
        except Exception as exc:  # never let a Sheets error fail the run
            logging.warning(f"Google Sheet update skipped: {exc}")

    summary = (
        f"Scanned {len(thread_ids)} thread(s), tracked {tracked}. "
        f"{len(due_list)} follow-up(s) due, {len(closed_list)} newly closed. "
        f"Digest emailed: {sent}. Sheet rows: {sheet_rows}."
    )
    logging.info(summary)
    return summary


@app.timer_trigger(
    schedule="0 0 8 * * *",  # NCRONTAB: sec min hour day month day-of-week -> 8:00 AM
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def daily_followup(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.info("Timer is past due — running now.")
    run_agent()


@app.route(route="run-now", auth_level=func.AuthLevel.FUNCTION)
def run_now(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger for testing: GET/POST the function URL (with its key)."""
    try:
        summary = run_agent()
        return func.HttpResponse(summary, status_code=200)
    except Exception as exc:  # surface errors to the caller during setup
        logging.exception("run_now failed")
        return func.HttpResponse(f"Error: {exc}", status_code=500)
