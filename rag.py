"""
Retrieval index over email text: chunk -> embed -> Postgres (pgvector + tsvector),
hybrid search fused with reciprocal rank fusion. No Gmail or Telegram here;
embeddings come from summarizer.py. Stores email text in Postgres (see AGENTS.md).
"""

import os
import re

import psycopg

from summarizer import embed_texts

TABLE = "email_chunks"
CHUNK_CHARS = 2000  # ~500 tokens; gemini-embedding-001 silently truncates at 2048
EMBED_BATCH = 20    # chunks per embedding call (verified with 20 full-size chunks)
CANDIDATES = 40     # per-retriever hits before fusion; = pgvector's default hnsw.ef_search
SNIPPET_CHARS = 300

_QUOTE_START = re.compile(
    r"^On\b[^\n]{0,300}(?:\n[^\n]{0,300})?\bwrote:[ \t]*$"  # Gmail/Apple, possibly wrapped
    r"|^(?i:-{2,}\s*original message\s*-{2,})"
    r"|^From:[^\n]*\n(?:Sent|Date):"                       # Outlook reply header
    r"|^-- ?$"                                             # signature delimiter
    r"|^Sent from my \w+",
    re.M,
)


def strip_quotes(body):
    """Drop quoted reply history and signatures; keep only what this message adds."""
    # ponytail: regex heuristics, English clients only ("Le ... a écrit" survives), and inline
    # replies lose the quoted context they answer. get_email still returns the raw body.
    body = body.replace("\r\n", "\n").replace("\x00", "")
    m = _QUOTE_START.search(body)
    if m:
        body = body[:m.start()]
    lines = [line for line in body.split("\n") if not line.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _split(text, size=CHUNK_CHARS):
    # ponytail: chars/4 token estimate and no overlap; dense scripts (CJK) can near the
    # 2048-token cap, and a fact split across a boundary is only half in each chunk.
    pieces = []
    while len(text) > size:
        cut = text.rfind("\n\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut <= 0:
            cut = size
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    pieces.append(text)
    return [p for p in pieces if p]


def chunk_email(e):
    """[(chunk_idx, text)] of the stripped body; [] if nothing is left after stripping."""
    return list(enumerate(_split(strip_quotes(e["body"] or ""))))


def _prefix(e):
    return f"From: {e['from']}\nDate: {e['date']}\nSubject: {e['subject']}\n\n"


def _vec(v):
    return "[" + ",".join(map(str, v)) + "]"


_ready = set()


def _conn():
    # ponytail: a fresh connection per call, no pool; fine at poll/chat rates.
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, prepare_threshold=0)
    if TABLE not in _ready:
        _setup(conn)
        _ready.add(TABLE)
    return conn


def _setup(conn):
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            gmail_id text NOT NULL,
            chunk_idx int NOT NULL,
            sender text NOT NULL,
            recipient text NOT NULL,
            date text NOT NULL,
            subject text NOT NULL,
            text text NOT NULL,
            embedding vector(768) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS
                (to_tsvector('english', sender || ' ' || subject || ' ' || "text")) STORED,
            UNIQUE (gmail_id, chunk_idx)
        )""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_embedding_idx ON {TABLE} USING hnsw (embedding vector_cosine_ops)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_tsv_idx ON {TABLE} USING gin (tsv)")


def index_emails(emails):
    """Chunk, embed and store emails (parsed dicts from gmail.py). Idempotent. Returns chunks stored."""
    rows = [(e, idx, piece) for e in emails for idx, piece in chunk_email(e)]

    if not rows:
        return 0

    vectors = []
    for i in range(0, len(rows), EMBED_BATCH):
        batch = rows[i:i + EMBED_BATCH]
        vectors += embed_texts([_prefix(e) + piece for e, _, piece in batch], "RETRIEVAL_DOCUMENT")

    clean = lambda s: (s or "").replace("\x00", "")
    with _conn() as conn, conn.transaction(), conn.cursor() as cur:
        # One transaction: an email is either fully indexed or not at all (backfill skips by id).
        cur.executemany(
            f"INSERT INTO {TABLE} (gmail_id, chunk_idx, sender, recipient, date, subject, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT (gmail_id, chunk_idx) DO NOTHING",
            [
                (e["id"], idx, clean(e["from"]), clean(e["to"]), clean(e["date"]), clean(e["subject"]), piece, _vec(v))
                for (e, idx, piece), v in zip(rows, vectors)
            ],
        )

    return len(rows)


def indexed_ids():
    with _conn() as conn:
        return {r[0] for r in conn.execute(f"SELECT DISTINCT gmail_id FROM {TABLE}")}


def rrf(rankings, k=60):
    """Reciprocal rank fusion of ranked id lists; duplicates within a list count once."""
    scores = {}
    for ranking in rankings:
        for rank, id_ in enumerate(dict.fromkeys(ranking), 1):
            scores[id_] = scores.get(id_, 0) + 1 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)


def _or_query(query):
    # websearch_to_tsquery ANDs words, and an AND over a whole question matches nothing.
    return " or ".join(w for w in re.findall(r"\w+", query) if w.lower() != "or")


def semantic_search(query, max_results=10):
    """Hybrid vector + full-text search over indexed mail. Same dict shape as gmail.search_emails."""
    qvec = _vec(embed_texts([query], "RETRIEVAL_QUERY")[0])
    cols = "gmail_id, sender, recipient, date, subject, text"

    with _conn() as conn:
        by_vector = conn.execute(
            f"SELECT {cols} FROM {TABLE} ORDER BY embedding <=> %s::vector LIMIT {CANDIDATES}", (qvec,)
        ).fetchall()
        by_text = conn.execute(
            f"SELECT {cols} FROM {TABLE}, websearch_to_tsquery('english', %s) q "
            f"WHERE tsv @@ q ORDER BY ts_rank(tsv, q) DESC LIMIT {CANDIDATES}",
            (_or_query(query),),
        ).fetchall()

    best = {}  # gmail_id -> its first-seen (best-ranked) chunk, for the snippet
    for row in by_vector + by_text:
        best.setdefault(row[0], row)

    ids = rrf([[r[0] for r in by_vector], [r[0] for r in by_text]])[:max_results]
    return [
        {
            "id": i, "from": best[i][1], "to": best[i][2], "date": best[i][3], "subject": best[i][4],
            "snippet": " ".join(best[i][5].split())[:SNIPPET_CHARS],
        }
        for i in ids
    ]
