import email
import imaplib
import os
from email.header import decode_header

IMAP_HOST = "imap.gmail.com"


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
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)

                if payload:
                    return payload.decode(
                        part.get_content_charset() or "utf-8",
                        errors="ignore"
                    ).strip()

        return ""

    payload = msg.get_payload(decode=True)

    if not payload:
        return ""

    return payload.decode(
        msg.get_content_charset() or "utf-8",
        errors="ignore"
    ).strip()


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
    Fetch and return unseen INBOX emails, marking them as seen.
    On the very first call, the existing unseen backlog is marked seen
    without being returned, so only mail arriving after that is summarized.
    """

    conn = _connect()

    try:
        _, data = conn.search(None, "UNSEEN")
        uids = data[0].split()

        first_run = not os.path.exists(BASELINE_FILE)

        if first_run:
            if uids:
                conn.store(
                    b",".join(uids), "+FLAGS", "\\Seen"
                )
            open(BASELINE_FILE, "w").close()
            return []

        emails = []

        for uid in uids:
            _, msg_data = conn.fetch(uid, "(RFC822)")
            raw_bytes = msg_data[0][1]
            emails.append(_parse_message(uid.decode(), raw_bytes))

        return emails
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
