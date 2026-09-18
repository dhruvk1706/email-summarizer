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


if __name__ == "__main__":
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        STATE_DB = tmp.name

    assert not is_delivered("123")
    mark_delivered("123")
    assert is_delivered("123")
    assert not is_delivered("456")
    os.remove(STATE_DB)
    print("ok")
