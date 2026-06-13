"""Gmail auth for the cloud (Azure Functions).

Unlike the local version, there is no interactive browser flow here. The OAuth
token you generated locally (token.json) is stored in the GMAIL_TOKEN_JSON app
setting. At runtime we load it and silently refresh the access token using the
long-lived refresh token.
"""
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_credentials():
    raw = os.environ.get("GMAIL_TOKEN_JSON")
    if not raw:
        raise RuntimeError(
            "GMAIL_TOKEN_JSON app setting is missing. Generate token.json locally "
            "(run main.py once) and paste its contents into the GMAIL_TOKEN_JSON "
            "application setting."
        )
    info = json.loads(raw)
    creds = Credentials.from_authorized_user_info(info, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Stored Gmail token is invalid and cannot be refreshed. Re-run the "
                "local OAuth flow and update GMAIL_TOKEN_JSON. (Make sure the Google "
                "OAuth consent screen is PUBLISHED so the refresh token doesn't expire.)"
            )

    return creds


def get_service():
    return build("gmail", "v1", credentials=get_credentials())


def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials())
