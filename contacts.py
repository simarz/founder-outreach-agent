"""Editable name/company overrides.

contacts.csv is the hybrid layer: the agent auto-fills name + company from the
email, but anything you type into contacts.csv wins on the next run. Open it in
Excel/Notepad anytime to correct a name or company.
"""
import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_FILE = os.path.join(BASE_DIR, "contacts.csv")


def load_contacts():
    """email -> {name, company}."""
    data = {}
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                email = (r.get("email") or "").strip().lower()
                if email:
                    data[email] = {
                        "name": (r.get("name") or "").strip(),
                        "company": (r.get("company") or "").strip(),
                    }
    return data


def save_contacts(contacts):
    with open(CONTACTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["email", "name", "company"])
        for email in sorted(contacts):
            w.writerow([email, contacts[email]["name"], contacts[email]["company"]])
