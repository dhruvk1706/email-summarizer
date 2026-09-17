from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
import os


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _decode_body(data):
    if not data:
        return ""

    try:
        return base64.urlsafe_b64decode(data).decode(
            "utf-8",
            errors="ignore"
        )
    except Exception:
        return ""


def _extract_body(payload):
    """
    Extract the plain-text body from a Gmail message.
    Handles both simple and multipart messages.
    """

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return _decode_body(payload.get("body", {}).get("data"))

    for part in payload.get("parts", []):
        body = _extract_body(part)

        if body:
            return body

    return ""


def _parse_message(message):
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    headers_dict = {
        header["name"].lower(): header["value"]
        for header in headers
    }

    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": headers_dict.get("from", ""),
        "to": headers_dict.get("to", ""),
        "subject": headers_dict.get("subject", ""),
        "date": headers_dict.get("date", ""),
        "body": _extract_body(payload).strip(),
    }


def get_email_by_id(message_id):
    """
    Fetch one specific Gmail message by its message ID.
    """

    service = get_gmail_service()

    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    if "CATEGORY_PERSONAL" not in message.get("labelIds", []):
        return None

    return _parse_message(message)


def get_latest_emails(max_results=5):
    """
    Fetch the latest emails from Gmail.
    Kept for backwards compatibility with the current app.
    """

    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    emails = []

    for message in messages:
        email = get_email_by_id(message["id"])
        emails.append(email)

    return emails

def get_new_message_ids(start_history_id):
    service = get_gmail_service()

    response = service.users().history().list(
        userId="me",
        startHistoryId=start_history_id,
        historyTypes=["messageAdded"],
    ).execute()

    message_ids = []

    for history in response.get("history", []):
        for message_added in history.get("messagesAdded", []):
            message_ids.append(
                message_added["message"]["id"]
            )

    return message_ids

def get_current_history_id():
    service = get_gmail_service()

    profile = service.users().getProfile(
        userId="me"
    ).execute()

    return profile["historyId"]