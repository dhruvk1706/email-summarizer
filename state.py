import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

STATE_DB = os.getenv("STATE_DB", "state.db")

# ponytail: keyed on IMAP uid alone, which is only unique within the mailbox's
# current UIDVALIDITY epoch. Fine for a single Gmail account where UIDVALIDITY
# essentially never changes; if it ever does, key on (uidvalidity, uid) instead.


@contextmanager
def _connect():
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS delivered "
            "(uid TEXT PRIMARY KEY, delivered_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telegram_messages "
            "(message_id INTEGER PRIMARY KEY, uid TEXT NOT NULL)"
        )
        yield conn
    finally:
        conn.close()


def is_delivered(uid):
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM delivered WHERE uid = ?", (uid,)
        ).fetchone()
        return row is not None


def mark_delivered(uid):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO delivered (uid, delivered_at) VALUES (?, ?)",
            (uid, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def record_sent_message(message_id, uid):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO telegram_messages (message_id, uid) VALUES (?, ?)",
            (message_id, uid),
        )
        conn.commit()


def get_uid_for_message(message_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT uid FROM telegram_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row[0] if row else None


if __name__ == "__main__":
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        STATE_DB = tmp.name

    assert not is_delivered("123")
    mark_delivered("123")
    assert is_delivered("123")
    assert not is_delivered("456")

    assert get_uid_for_message(999) is None
    record_sent_message(999, "42")
    assert get_uid_for_message(999) == "42"

    os.remove(STATE_DB)
    print("ok")
