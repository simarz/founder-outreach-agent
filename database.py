"""Local SQLite store of tracked outreach threads.

This is mostly a durable cache of what we've seen so you have a history of
every founder you've emailed and their reply status. Follow-up status is
recomputed from Gmail on each run, so the DB never goes stale.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "tracking.db")


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked (
            thread_id          TEXT PRIMARY KEY,
            recipient_email    TEXT NOT NULL,
            recipient_name     TEXT,
            company            TEXT,
            subject            TEXT,
            first_sent_date    TEXT,
            last_sent_date     TEXT,
            replied            INTEGER DEFAULT 0,
            replied_date       TEXT,
            last_notified_date TEXT,
            status             TEXT,
            followups_sent     INTEGER DEFAULT 0,
            closed_notified    INTEGER DEFAULT 0
        )
        """
    )
    # Migrate older databases that predate the follow-up-limit columns.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tracked)").fetchall()}
    for col, decl in (
        ("status", "TEXT"),
        ("followups_sent", "INTEGER DEFAULT 0"),
        ("closed_notified", "INTEGER DEFAULT 0"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE tracked ADD COLUMN {col} {decl}")
    conn.commit()
    conn.close()


def upsert_thread(row):
    """Insert or update a tracked thread. first_sent_date and closed_notified are
    preserved across updates."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO tracked (thread_id, recipient_email, recipient_name, company,
                             subject, first_sent_date, last_sent_date, replied,
                             replied_date, status, followups_sent)
        VALUES (:thread_id, :recipient_email, :recipient_name, :company,
                :subject, :first_sent_date, :last_sent_date, :replied,
                :replied_date, :status, :followups_sent)
        ON CONFLICT(thread_id) DO UPDATE SET
            recipient_email = excluded.recipient_email,
            recipient_name  = excluded.recipient_name,
            company         = excluded.company,
            subject         = excluded.subject,
            last_sent_date  = excluded.last_sent_date,
            replied         = excluded.replied,
            replied_date    = excluded.replied_date,
            status          = excluded.status,
            followups_sent  = excluded.followups_sent
        """,
        row,
    )
    conn.commit()
    conn.close()


def get_closed_notified(thread_id):
    """True if we've already sent the one-time 'closed' notice for this thread."""
    conn = get_conn()
    row = conn.execute(
        "SELECT closed_notified FROM tracked WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    conn.close()
    return bool(row["closed_notified"]) if row else False


def mark_notified(thread_id, date_str):
    conn = get_conn()
    conn.execute(
        "UPDATE tracked SET last_notified_date = ? WHERE thread_id = ?",
        (date_str, thread_id),
    )
    conn.commit()
    conn.close()


def mark_closed_notified(thread_id):
    conn = get_conn()
    conn.execute(
        "UPDATE tracked SET closed_notified = 1 WHERE thread_id = ?", (thread_id,)
    )
    conn.commit()
    conn.close()


def all_threads():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tracked ORDER BY last_sent_date DESC"
    ).fetchall()
    conn.close()
    return rows
