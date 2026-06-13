"""Builds and sends the daily follow-up digest email to yourself."""
import base64
from email.mime.text import MIMEText


def _due_table(due_list):
    rows = []
    for d in due_list:
        rows.append(
            "<tr>"
            f"<td style='padding:6px 10px'>{d['company'] or '-'}</td>"
            f"<td style='padding:6px 10px'><a href='mailto:{d['email']}'>{d['email']}</a></td>"
            f"<td style='padding:6px 10px'>{d['sent']}</td>"
            f"<td style='padding:6px 10px;text-align:center'>{d['days']}</td>"
            f"<td style='padding:6px 10px;text-align:center'>{d['followups_sent']}</td>"
            "</tr>"
        )
    return (
        "<table style='border-collapse:collapse;border:1px solid #ddd;font-size:14px'>"
        "<thead><tr style='background:#f4f4f4;text-align:left'>"
        "<th style='padding:6px 10px'>Company</th>"
        "<th style='padding:6px 10px'>Email</th><th style='padding:6px 10px'>Last sent</th>"
        "<th style='padding:6px 10px'>Days ago</th><th style='padding:6px 10px'>Follow-ups sent</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _closed_table(closed_list):
    rows = []
    for d in closed_list:
        rows.append(
            "<tr>"
            f"<td style='padding:6px 10px'>{d['company'] or '-'}</td>"
            f"<td style='padding:6px 10px'><a href='mailto:{d['email']}'>{d['email']}</a></td>"
            f"<td style='padding:6px 10px'>{d['sent']}</td>"
            "</tr>"
        )
    return (
        "<table style='border-collapse:collapse;border:1px solid #ddd;font-size:14px'>"
        "<thead><tr style='background:#f4f4f4;text-align:left'>"
        "<th style='padding:6px 10px'>Company</th>"
        "<th style='padding:6px 10px'>Email</th><th style='padding:6px 10px'>Last sent</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def send_digest(service, to_email, due_list, closed_list, followup_days, max_followups):
    """Send the digest. Returns True if an email was sent.

    due_list    = founders to follow up with now.
    closed_list = founders just closed out (no reply after max_followups); shown
                  once so you know tracking stopped, then never again.
    """
    if not due_list and not closed_list:
        return False

    sections = []
    if due_list:
        sections.append(
            "<h2 style='margin-bottom:4px'>Follow-up reminders</h2>"
            f"<p style='margin-top:0;color:#555'>{len(due_list)} founder(s) "
            f"haven't replied in {followup_days}+ days.</p>" + _due_table(due_list)
        )
    if closed_list:
        sections.append(
            "<h2 style='margin-bottom:4px;margin-top:24px'>Closed — no reply</h2>"
            f"<p style='margin-top:0;color:#555'>{len(closed_list)} founder(s) didn't "
            f"reply after {max_followups} follow-up(s). Tracking has stopped for these "
            "— you won't be reminded again.</p>" + _closed_table(closed_list)
        )

    html = (
        "<div style='font-family:Arial,Helvetica,sans-serif;color:#222'>"
        + "".join(sections)
        + "<p style='color:#888;font-size:12px;margin-top:16px'>"
        "Sent by your Founder Follow-up Agent. The clock resets automatically once "
        "you reply in a thread; tracking stops after "
        f"{max_followups} unanswered follow-up(s).</p></div>"
    )

    # Subject reflects what's inside.
    if due_list and closed_list:
        subject = f"⏰ {len(due_list)} follow-up(s) due · {len(closed_list)} closed"
    elif due_list:
        subject = f"⏰ {len(due_list)} founder follow-up(s) due"
    else:
        subject = f"✓ {len(closed_list)} outreach closed (no reply)"

    msg = MIMEText(html, "html")
    msg["To"] = to_email
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return True
