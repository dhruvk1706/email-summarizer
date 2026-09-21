import email
import imaplib
import os
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from html import unescape

from state import is_delivered, mark_delivered

IMAP_HOST = "imap.gmail.com"


def _html_to_text(html):
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _decode(value):
    if not value:
        return ""

    parts = decode_header(value)
    decoded = ""

    for text, charset in parts:
        if isinstance(text, bytes):
            decoded += text.decode(charset or "utf-8", errors="ignore")
        else:
            decoded += text

    return decoded


def _extract_body(msg):
    if msg.is_multipart():
        html_fallback = ""

        for part in msg.walk():
            content_type = part.get_content_type()

            if content_type not in ("text/plain", "text/html"):
                continue

            payload = part.get_payload(decode=True)

            if not payload:
                continue

            text = payload.decode(
                part.get_content_charset() or "utf-8",
                errors="ignore"
            ).strip()

            if content_type == "text/plain":
                return text

            html_fallback = html_fallback or text

        return _html_to_text(html_fallback) if html_fallback else ""

    payload = msg.get_payload(decode=True)

    if not payload:
        return ""

    text = payload.decode(
        msg.get_content_charset() or "utf-8",
        errors="ignore"
    ).strip()

    if msg.get_content_type() == "text/html":
        return _html_to_text(text)

    return text


def _parse_message(uid, raw_bytes):
    msg = email.message_from_bytes(raw_bytes)

    return {
        "id": uid,
        "from": _decode(msg.get("From", "")),
        "to": _decode(msg.get("To", "")),
        "subject": _decode(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
        "body": _extract_body(msg),
    }


def _connect():
    imap_user = os.environ["GMAIL_IMAP_USER"]
    imap_password = os.environ["GMAIL_APP_PASSWORD"]

    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    conn.login(imap_user, imap_password)
    conn.select("INBOX")

    return conn


BASELINE_FILE = "baseline_established"


def get_new_emails():
    """
    Fetch and return recent INBOX emails (last 3 days), regardless of read
    state. Caller dedups against already-delivered uids (state.py), so
    reading an email in Gmail directly no longer hides it from summarization.
    On the very first call, the recent backlog is recorded as the baseline
    without being returned, so only mail arriving after that is summarized.
    """

    conn = _connect()

    try:
        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%d-%b-%Y")
        _, data = conn.search(None, "SINCE", since)
        uids = data[0].split()

        first_run = not os.path.exists(BASELINE_FILE)

        if first_run:
            for uid in uids:
                mark_delivered(uid.decode())
            open(BASELINE_FILE, "w").close()
            return []

        emails = []

        for uid in uids:
            if is_delivered(uid.decode()):
                continue

            _, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
            raw_bytes = msg_data[0][1]
            emails.append(_parse_message(uid.decode(), raw_bytes))

        return emails
    finally:
        conn.logout()


def get_email_by_uid(uid):
    """
    Fetch and parse a single email by IMAP uid, without changing its seen state.
    Returns None if the uid no longer exists in the mailbox.
    """

    conn = _connect()

    try:
        _, msg_data = conn.fetch(uid.encode(), "(BODY.PEEK[])")

        if not msg_data or msg_data[0] is None:
            return None

        raw_bytes = msg_data[0][1]
        return _parse_message(uid, raw_bytes)
    finally:
        conn.logout()


def get_latest_emails(max_results=5):
    """
    Fetch the latest emails from Gmail (read or unread), most recent first.
    """

    conn = _connect()

    try:
        _, data = conn.search(None, "ALL")
        uids = data[0].split()[-max_results:]

        emails = []

        for uid in reversed(uids):
            _, msg_data = conn.fetch(uid, "(RFC822)")
            raw_bytes = msg_data[0][1]
            emails.append(_parse_message(uid.decode(), raw_bytes))

        return emails
    finally:
        conn.logout()
