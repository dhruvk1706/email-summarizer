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


def _parse_message(gmail_id, raw_bytes):
    msg = email.message_from_bytes(raw_bytes)

    return {
        "id": gmail_id,
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


# Emails are identified everywhere by Gmail's X-GM-MSGID: permanent, and the
# same in INBOX and All Mail (unlike IMAP sequence numbers or per-folder UIDs).
# v2: ids switched from sequence numbers to X-GM-MSGID, so re-baseline once.
BASELINE_FILE = "baseline_established_v2"
SEARCH_BYTES = 30000  # partial fetch for search snippets; enough for the text part


def _fetch(conn, uid, part="BODY.PEEK[]"):
    """UID FETCH one message; returns (gmail_id, raw_bytes) or None."""
    _, data = conn.uid("FETCH", uid, f"(X-GM-MSGID {part})")
    item = next((d for d in data if isinstance(d, tuple)), None)

    if item is None:
        return None

    gmail_id = re.search(rb"X-GM-MSGID (\d+)", item[0]).group(1).decode()
    return gmail_id, item[1]


def _uid_search(conn, *criteria):
    _, data = conn.uid("SEARCH", *criteria)
    return data[0].split() if data and data[0] else []


def _select_all_mail(conn):
    # The All Mail folder name is localized ("[Google Mail]/All Mail" etc.),
    # so find it by its \All special-use flag.
    _, folders = conn.list()

    for line in folders:
        if b"\\All" in line:
            name = re.search(rb'"([^"]+)"$', line).group(1).decode()
            conn.select(f'"{name}"', readonly=True)
            return

    raise RuntimeError("All Mail folder not found (enable it for IMAP in Gmail settings)")


def get_new_emails():
    """
    Fetch and return recent INBOX emails (last 3 days), regardless of read
    state. Caller dedups against already-delivered ids (state.py), so
    reading an email in Gmail directly no longer hides it from summarization.
    On the very first call, the recent backlog is recorded as the baseline
    without being returned, so only mail arriving after that is summarized.
    """

    conn = _connect()

    try:
        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%d-%b-%Y")
        uids = _uid_search(conn, "SINCE", since)

        if not uids:
            return []

        _, data = conn.uid("FETCH", b",".join(uids), "(X-GM-MSGID)")
        ids = {
            re.search(rb"UID (\d+)", line).group(1): re.search(rb"X-GM-MSGID (\d+)", line).group(1).decode()
            for line in data if isinstance(line, bytes) and b"X-GM-MSGID" in line
        }

        if not os.path.exists(BASELINE_FILE):
            for gmail_id in ids.values():
                mark_delivered(gmail_id)
            open(BASELINE_FILE, "w").close()
            return []

        emails = []

        for uid in uids:
            gmail_id = ids.get(uid)

            if gmail_id is None or is_delivered(gmail_id):
                continue

            fetched = _fetch(conn, uid)

            if fetched:
                emails.append(_parse_message(*fetched))

        return emails
    finally:
        conn.logout()


def search_emails(query, max_results=10):
    """
    Search All Mail with Gmail search syntax (e.g. 'from:john newer_than:7d').
    Empty query = most recent mail. Returns newest-first metadata + a short
    snippet; use get_email_by_id for the full body.
    """

    conn = _connect()

    try:
        _select_all_mail(conn)

        if query.strip():
            # Sent as an IMAP literal: no quoting/escaping, CRLF can't inject, UTF-8 ok.
            conn.literal = query.encode("utf-8")
            uids = _uid_search(conn, "CHARSET", "UTF-8", "X-GM-RAW")
        else:
            uids = _uid_search(conn, "ALL")

        results = []

        # ponytail: one FETCH per hit (max ~20 round trips); batch if it's slow.
        for uid in reversed(uids[-max_results:]):
            fetched = _fetch(conn, uid, f"BODY.PEEK[]<0.{SEARCH_BYTES}>")

            if fetched:
                email_data = _parse_message(*fetched)
                email_data["snippet"] = " ".join(email_data.pop("body").split())[:300]
                results.append(email_data)

        return results
    finally:
        conn.logout()


def get_email_by_id(gmail_id):
    """
    Fetch one email from All Mail by Gmail id, without changing its seen state.
    Returns None if no such email exists.
    """

    gmail_id = str(gmail_id).strip()

    if not (gmail_id.isascii() and gmail_id.isdigit()):
        return None

    conn = _connect()

    try:
        _select_all_mail(conn)
        uids = _uid_search(conn, "X-GM-MSGID", gmail_id)

        if not uids:
            return None

        fetched = _fetch(conn, uids[0])
        return _parse_message(*fetched) if fetched else None
    finally:
        conn.logout()
