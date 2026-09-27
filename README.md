# Founder Follow-up Agent

Tracks the startup founders you email in Gmail and reminds you — by email — when
someone hasn't replied in 7 days.

You tag outreach emails with a Gmail label (`founders`). Each day the agent
scans those threads, records who you emailed (name, company, email, send date),
checks whether they replied, and emails you a digest of anyone overdue for a
follow-up. The 7-day clock **resets automatically** whenever you reply again in a
thread.

---

## What you get

| File | Purpose |
|------|---------|
| `main.py` | The agent. Scans Gmail, updates records, sends the digest. |
| `status.py` | Prints everyone you've tracked and their status (no Gmail call). |
| `contacts.csv` | Auto-generated. Edit names/companies here — your edits always win. |
| `tracking.db` | Local SQLite history of every founder you've emailed. |
| `config.json` | Settings: label name, follow-up days, where to send reminders. |

---

## Setup (one time, ~10 minutes)

### 1. Install dependencies

```powershell
cd "C:\Users\mineb\Desktop\Email Tracking Agent"
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### 2. Get Gmail API credentials

The agent talks to Gmail through Google's official API. You create a free OAuth
client once:

1. Go to <https://console.cloud.google.com/> and create a project (any name).
2. Search **"Gmail API"** in the top search bar → **Enable**.
3. Go to **APIs & Services → OAuth consent screen**:
   - User type: **External** → Create.
   - Fill in the app name and your email where required, then Save and Continue
     through the screens.
   - On **Test users**, click **Add Users** and add `your-email@example.com`.
     (While the app is in "Testing", only listed test users can authorize it —
     that's fine, it's just you.)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app** → Create.
   - Click **Download JSON**.
5. Save that file in this folder as exactly **`credentials.json`**.

### 3. Create the Gmail label and tag some emails

In Gmail, create a label named **`founders`** (left sidebar → "+ Create new
label"). Apply it to the outreach emails you want tracked — you can apply a label
to a message right after sending, or select sent messages and label them in bulk.

> Want a different label name? Change `"label_name"` in `config.json`.

### 4. First run (authorizes the app)

```powershell
.\.venv\Scripts\python.exe main.py
```

A browser window opens asking you to sign in and grant access. You may see an
"unverified app" warning — click **Advanced → Go to (app)** since it's your own
app. After you approve, a `token.json` is saved and future runs are silent.

### 5. Schedule it to run daily

```powershell
powershell -ExecutionPolicy Bypass -File .\register_task.ps1
```

This creates a Windows Scheduled Task **FounderFollowupAgent** that runs every
day at 8:00 AM. Edit the time inside `register_task.ps1` and re-run to change it.

Run it on demand anytime:

```powershell
Start-ScheduledTask -TaskName FounderFollowupAgent
```

---

## Daily use

- **You:** send outreach, apply the `founders` label.
- **Agent (each morning):** scans labeled threads, emails you a digest titled
  "⏰ N founder follow-up(s) due" listing name, company, email, and how long it's
  been. No email is sent on days when nothing is due.
- **To fix a name/company:** open `contacts.csv`, edit the row, save. The
  correction sticks on every future run.
- **To see everything at a glance:**

  ```powershell
  .\.venv\Scripts\python.exe status.py
  ```

---

## Settings (`config.json`)

Copy the template and fill in your email (your real `config.json` is git-ignored):

```powershell
copy config.example.json config.json
```

```json
{
  "label_name": "founders",
  "followup_days": 7,
  "max_followups": 2,
  "notify_email": "your-email@example.com"
}
```

- `label_name` — which Gmail label marks tracked outreach.
- `followup_days` — days of silence before a follow-up is flagged.
- `max_followups` — stop reminding after this many unanswered follow-ups (`2` =
  initial email + 2 follow-ups, then the thread is closed out).
- `notify_email` — where the daily digest is sent.

### Two categories: New outreach vs Replied

Every tracked thread is in one of two categories:

- **New outreach** — the founder hasn't engaged yet. Reminded after
  `followup_days` of silence; closed out ("Closed — no reply") after
  `max_followups` unanswered follow-ups.
- **Replied** — the founder has engaged: they replied in the thread, **or** you
  tagged the thread with the **`responded` label** (for replies that arrive
  outside the thread — a new email, LinkedIn, a call). Replied threads stay on
  the **same 7-day cadence**: whenever the conversation goes quiet for
  `followup_days` (whoever spoke last), you're reminded to follow up. They are
  **never** closed out by the follow-up cap — that's for ghosts, not live
  conversations.

The `responded` label can be nested under `founders` (Gmail shows it as
`founders/responded`) — the agent matches it either way. The digest marks each
reminder with its stage (Replied vs New outreach), and the Google Sheet keeps
the categories on separate tabs: the main tab for outreach, a **Replied** tab
for engaged founders. Tracking stops entirely only when a thread is closed as
no-reply or you remove the `founders` label.

When a thread hits the follow-up limit, it appears **once** in the digest under
"Closed — no reply" so you know it stopped, then never again.

---

## Export to Google Sheets (optional)

The agent can mirror its full tracking table into a Google Sheet that you own.
Every run **clears and rewrites** the sheet, so it's always an exact snapshot —
Name · Company · Email · Subject · First sent · Last sent · Follow-ups sent ·
Status · Replied date · Last updated, sorted with "follow up now" at the top.

**Setup:**
1. Create a blank sheet at <https://sheets.new> (signed in as the same Google
   account). Leave the first tab named `Sheet1`.
2. Copy its **ID** from the URL — the long string between `/d/` and `/edit`:
   `https://docs.google.com/spreadsheets/d/`**`THIS_IS_THE_ID`**`/edit`
3. Put it in `config.json` as `"sheet_id": "THIS_IS_THE_ID"`.
4. **Re-authorize once** — the agent now needs Google Sheets access, so the old
   token won't work for it. Delete `token.json` and run `main.py` again to grant
   the new permission:
   ```powershell
   del token.json
   .\.venv\Scripts\python.exe main.py
   ```

Leave `sheet_id` empty to disable. Sheet updates are best-effort — if Sheets is
unreachable, the run still completes and emails normally.

> Using the Azure deployment too? See `azure-function/README_AZURE.md` — set the
> `SHEET_ID` app setting and update `GMAIL_TOKEN_JSON` with the new token.

## How reply detection works

For each labeled thread the agent finds your **most recent** message and checks
whether the founder sent anything after it. If not, and it's been
`followup_days`+ days, they're flagged. Because it keys off your *last* message,
following up resets the clock with no extra bookkeeping.

---

## Privacy & security

- Everything runs locally on your PC. No third-party servers.
- `credentials.json` and `token.json` are secrets — they're git-ignored. Don't
  share them.
- Scopes requested: read-only Gmail access (to scan threads) and send (to email
  you the digest). The agent never deletes or modifies your mail.
