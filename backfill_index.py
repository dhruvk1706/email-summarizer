"""
Index past mail into the semantic search table (rag.py). Resumable: emails
already indexed are skipped, so rerun after a crash or quota error.

Usage: python backfill_index.py --months 6
"""

import argparse
import sys
from datetime import date, timedelta

import gmail
import rag

BATCH = 50  # emails per index_emails call (embedding calls are batched inside)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--months", type=int, required=True, help="how far back to index")
    args = parser.parse_args()

    # ponytail: a month is 30 days here; Gmail's SINCE is day-granular anyway.
    since = date.today() - timedelta(days=30 * args.months)
    done = rag.indexed_ids()
    print(f"Indexing All Mail since {since}; {len(done)} email(s) already indexed, skipping those.")

    seen = indexed = chunks = 0
    batch = []

    def flush():
        nonlocal indexed, chunks
        n = rag.index_emails(batch)
        # ponytail: emails empty after stripping store no rows, so each rerun refetches them.
        indexed += sum(1 for e in batch if rag.chunk_email(e))
        chunks += n
        print(f"seen {seen}, indexed {indexed}, chunks {chunks}, empty {seen - indexed}; at {batch[-1]['date']}")
        batch.clear()

    for e in gmail.iter_all_mail_since(since, skip=done.__contains__):
        seen += 1
        batch.append(e)
        if len(batch) >= BATCH:
            flush()

    if batch:
        flush()

    print(f"Done: {indexed} email(s) indexed in {chunks} chunk(s); {seen - indexed} empty after stripping.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
