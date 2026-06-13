"""Gmail OAuth handling.

On first run this opens a browser so you can authorize the app. The resulting
token is cached in token.json so later runs are non-interactive (important for
the daily scheduled task).
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# readonly = scan sent mail + threads + labels; send = deliver the digest email;
# spreadsheets = write the tracking table to your Google Sheet.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_credentials():
    """Return valid OAuth credentials, running the browser flow if needed."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "Missing credentials.json next to this script.\n"
                    "Download your OAuth client (Desktop app) from the Google "
                    "Cloud Console and save it here as credentials.json. "
                    "See README.md for step-by-step instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def get_service():
    """Return an authenticated Gmail API service client."""
    return build("gmail", "v1", credentials=get_credentials())


def get_sheets_service():
    """Return an authenticated Google Sheets API service client."""
    return build("sheets", "v4", credentials=get_credentials())
