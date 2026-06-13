"""Durable state in Azure Blob Storage.

Azure Functions have an ephemeral filesystem, so the name/company overrides and
the tracking history live in a blob container instead of local files. The
storage connection string (AzureWebJobsStorage) already exists in every Function
App, so we reuse it.

State is kept in two blobs:
  - contacts.csv  : editable email,name,company overrides (download/edit/re-upload)
  - tracking.json : history of every tracked thread + reply status
"""
import csv
import io
import json
import os

from azure.storage.blob import BlobServiceClient

CONNECTION_STRING = os.environ.get("AzureWebJobsStorage")
CONTAINER = os.environ.get("STATE_CONTAINER", "followup-state")
CONTACTS_BLOB = "contacts.csv"
TRACKING_BLOB = "tracking.json"


def _container_client():
    svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    container = svc.get_container_client(CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass  # already exists
    return container


def _read_blob(name):
    try:
        return _container_client().download_blob(name).readall().decode("utf-8")
    except Exception:
        return None


def _write_blob(name, text):
    _container_client().upload_blob(name, text.encode("utf-8"), overwrite=True)


# ---- contacts overrides (email -> {name, company}) -------------------------

def load_contacts():
    text = _read_blob(CONTACTS_BLOB)
    data = {}
    if text:
        for r in csv.DictReader(io.StringIO(text)):
            email = (r.get("email") or "").strip().lower()
            if email:
                data[email] = {
                    "name": (r.get("name") or "").strip(),
                    "company": (r.get("company") or "").strip(),
                }
    return data


def save_contacts(contacts):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "name", "company"])
    for email in sorted(contacts):
        w.writerow([email, contacts[email]["name"], contacts[email]["company"]])
    _write_blob(CONTACTS_BLOB, buf.getvalue())


# ---- tracking history (thread_id -> record) --------------------------------

def load_tracking():
    text = _read_blob(TRACKING_BLOB)
    if text:
        try:
            return json.loads(text)
        except Exception:
            return {}
    return {}


def save_tracking(records):
    _write_blob(TRACKING_BLOB, json.dumps(records, indent=2))
