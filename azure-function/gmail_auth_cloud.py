"""Gmail auth for the cloud (Azure Functions).

Unlike the local version, there is no interactive browser flow here. The OAuth
token you generated locally (token.json) is stored in the GMAIL_TOKEN_JSON app
setting. At runtime we load it and silently refresh the access token using the
long-lived refresh token.
"""
import json
import logging
import os
import time

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _refresh_with_retries(creds, attempts=3, delay=5):
    """Refresh the access token, retrying transient failures.

    The daily timer run is a cold start, so the first outbound HTTPS call (this
    refresh) can fail on a momentary network/DNS blip before the worker is fully
    warm. Retrying a couple of times a few seconds apart recovers in-process.
    A genuinely dead token (invalid_grant) is NOT retried — that needs re-auth.
    """
    last_error = None
    for attempt in range(attempts):
        try:
            creds.refresh(Request())
            return
        except RefreshError as exc:
            if "invalid_grant" in str(exc).lower():
                raise  # token is actually revoked/expired — retrying won't help
            last_error = exc
        except Exception as exc:  # transport/timeout/DNS — typical cold-start blip
            last_error = exc
        if attempt < attempts - 1:
            logging.warning(
                "Token refresh attempt %d failed (%s); retrying in %ds...",
                attempt + 1, type(last_error).__name__, delay,
            )
            time.sleep(delay)
    raise last_error


def get_credentials():
    raw = os.environ.get("GMAIL_TOKEN_JSON")
    if not raw:
        raise RuntimeError(
            "GMAIL_TOKEN_JSON app setting is missing. Generate token.json locally "
            "(run main.py once) and paste its contents into the GMAIL_TOKEN_JSON "
            "application setting."
        )
    try:
        info = json.loads(raw)
    except ValueError as exc:  # includes json.JSONDecodeError
        raise RuntimeError(
            f"GMAIL_TOKEN_JSON is set but is not valid JSON (length {len(raw)}). "
            "Re-paste the FULL contents of a freshly generated token.json into the "
            "GMAIL_TOKEN_JSON app setting (use the Portal to avoid truncation)."
        ) from exc

    try:
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    except ValueError as exc:
        raise RuntimeError(
            "GMAIL_TOKEN_JSON parsed as JSON but is missing required fields "
            "(client_id/client_secret/refresh_token). Regenerate token.json locally "
            "and re-paste its full contents."
        ) from exc

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            _refresh_with_retries(creds)
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
