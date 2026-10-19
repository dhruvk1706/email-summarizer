"""RAG checks: quote stripping, chunking, RRF, tool format; offline with a fake embedder.
The DB test runs only when DATABASE_URL is set (uses its own email_chunks_test table, dropped after).

Run: python test_rag.py
Live eval against real Gmail + Gemini + index (needs backfill first): python test_rag.py --live
"""

import os
import re
import sys
import zlib
from unittest.mock import patch

import rag
import tools

# Questions keyword search handles badly and semantic_search should now answer.
EVAL_QUESTIONS = [
    "Find the email where someone asked me to approve a budget.",
    "Did anyone send me a contract or agreement to sign?",
    "What travel bookings do I have coming up, like flights or hotels?",
    "Has anyone invited me to a job interview or asked about my availability for one?",
    "Are there any unpaid invoices or overdue payment reminders?",
    "Find the email about a refund I was promised.",
    "Across my receipts from the last three months, which shops did I buy from?",
    "Has anyone asked me to review a document or give feedback on something?",
    "Did I get any security alerts about a new sign-in or password change?",
    "Which emails talk about rescheduling or moving a meeting?",
    "What subscriptions am I paying for, based on the billing emails?",
    "Did anyone thank me for something recently? What for?",
    "Find the email with the address or directions for an event I'm going to.",
    "Has anyone complained about a problem or a delay with something I'm responsible for?",
    "What deadlines have people mentioned to me in recent emails?",
    "Did anyone share a link to a shared folder or document with me?",
    "Was there an email about a delivery being delayed or a package I missed?",
    "Has anyone asked me for a recommendation or a reference?",
]


def test_strip_gmail_quote_single_and_wrapped():
    body = "Sounds good, see you then.\n\nOn Mon, 1 Sep 2026 at 10:00, John <john@x.com> wrote:\n> Lunch on Friday?"
    assert rag.strip_quotes(body) == "Sounds good, see you then."
    wrapped = "Yes.\r\n\r\nOn Mon, 1 Sep 2026 at 10:00, John Smith\r\n<john.smith@example.com> wrote:\r\n> old"
    assert rag.strip_quotes(wrapped) == "Yes."


def test_strip_inline_quotes_signature_and_outlook():
    inline = "> Can you do Friday?\nFriday works.\n> And the budget?\nApproved."
    assert rag.strip_quotes(inline) == "Friday works.\nApproved."
    assert rag.strip_quotes("Thanks!\n-- \nJane Doe\nCEO") == "Thanks!"
    assert rag.strip_quotes("Done.\n\n-----Original Message-----\nFrom: a\nold stuff") == "Done."
    assert rag.strip_quotes("Done.\n\nFrom: Bob <b@x.com>\nSent: Monday\nold") == "Done."
    assert rag.strip_quotes("Ok\n\nSent from my iPhone") == "Ok"
    # "On ... wrote" mid-sentence is content, not a quote header.
    assert "wrote" in rag.strip_quotes("On reflection, I think Alice wrote: a great memo.\nYes")  # noqa
    assert rag.strip_quotes("> only quoted\n> stuff") == ""


def test_chunking_size_and_coverage():
    paragraphs = [" ".join(f"word{p}_{i}" for i in range(60)) for p in range(30)]
    body = "\n\n".join(paragraphs)
    chunks = rag.chunk_email({"body": body})
    assert len(chunks) > 1
    assert [i for i, _ in chunks] == list(range(len(chunks)))
    assert all(len(text) <= rag.CHUNK_CHARS for _, text in chunks)
    assert " ".join(t for _, t in chunks).split() == body.split()  # nothing lost or duplicated
    assert rag.chunk_email({"body": "x" * (rag.CHUNK_CHARS * 2 + 5)})[0][1] == "x" * rag.CHUNK_CHARS  # no spaces
    assert rag.chunk_email({"body": "Short note."}) == [(0, "Short note.")]
    assert rag.chunk_email({"body": "\n> quoted only\n"}) == []
    assert rag.chunk_email({"body": None}) == []


def test_rrf_ordering_and_dedupe():
    fused = rag.rrf([["a", "b", "c"], ["c", "d"]])
    assert fused[0] == "c"  # in both lists beats rank 1 in only one
    assert fused == ["c", "a", "b", "d"]
    # Repeats in one list (several chunks of one email) count once, and don't push others down.
    assert rag.rrf([["a", "a", "a", "b"], ["b"]]) == ["b", "a"]
    # k=60 flattens rank gaps: rank 2 in two lists (2/62) beats rank 1 in one (1/61)...
    assert rag.rrf([["a", "b"], ["c", "b"]])[0] == "b"
    # ...whereas with k=0 rank 1 once (1/1) ties rank 2 twice (1/2 + 1/2); ties keep first-seen order.
    assert rag.rrf([["a", "b"], ["c", "b"]], k=0) == ["a", "b", "c"]
    assert rag.rrf([[], []]) == []


def test_or_query():
    assert rag._or_query("approve the budget, or not?") == "approve or the or budget or not"
    assert rag._or_query("!!!") == ""


def test_tool_output_matches_search_emails_format():
    hit = {"id": "9", "from": "Ann", "to": "me", "date": "Tue", "subject": "Budget", "snippet": "please approve"}
    with patch.object(rag, "semantic_search", return_value=[hit]) as search:
        out = tools.semantic_search.invoke({"query": "budget approval", "max_results": 99})
    search.assert_called_once_with("budget approval", 20)
    assert out.startswith("id: 9\nFrom: Ann\n") and "Preview" in out and "please approve" in out
    with patch.object(rag, "semantic_search", return_value=[]):
        assert "No emails found" in tools.semantic_search.invoke({"query": "x"})


def fake_embed(texts, task_type):
    """Bag-of-words hashed into 768 dims: shared words -> higher cosine similarity."""
    vectors = []
    for text in texts:
        v = [0.0] * 768
        for w in re.findall(r"\w+", text.lower()):
            v[zlib.crc32(w.encode()) % 768] += 1.0
        v[0] += 0.01  # never a zero vector
        vectors.append(v)
    return vectors


def test_db_index_and_search():
    if not os.getenv("DATABASE_URL"):
        print("skip test_db_index_and_search: DATABASE_URL unset")
        return

    def mail(i, subject, body):
        return {"id": f"test-{i}", "from": f"Sender{i} <s{i}@x.com>", "to": "me", "date": "Mon, 1 Sep 2026",
                "subject": subject, "body": body}

    long_budget = "\n\n".join(["Please approve the marketing budget for Q4. " * 20] * 4)
    emails = [
        mail(1, "Q4 numbers", long_budget + "\n\nOn Sun, Bob wrote:\n> lunch pizza lunch pizza"),
        mail(2, "Lunch", "Pizza or sushi for lunch on Friday?"),
        mail(3, "Newsletter", "This week in gardening: tomatoes and roses."),
        mail(4, "Fwd", "> only quoted text"),
    ]

    with patch.object(rag, "TABLE", "email_chunks_test"), patch.object(rag, "embed_texts", fake_embed):
        try:
            n = rag.index_emails(emails)
            assert n == len(rag.chunk_email(emails[0])) + 2 and n > 3  # long email is multi-chunk; test-4 empty
            assert rag.index_emails(emails) == n  # rerun: ON CONFLICT, no duplicate rows
            with rag._conn() as conn:
                assert conn.execute("SELECT count(*) FROM email_chunks_test").fetchone()[0] == n
            assert rag.indexed_ids() == {"test-1", "test-2", "test-3"}

            hits = rag.semantic_search("who asked me to approve a budget?", 10)
            ids = [h["id"] for h in hits]
            assert ids[0] == "test-1" and len(ids) == len(set(ids))  # deduped by gmail_id
            assert "approve" in hits[0]["snippet"] and len(hits[0]["snippet"]) <= rag.SNIPPET_CHARS
            assert hits[0]["subject"] == "Q4 numbers" and hits[0]["from"].startswith("Sender1")
            # Stripped quote ("lunch pizza") is not indexed, so lunch ranks test-2 first.
            assert rag.semantic_search("pizza lunch", 1)[0]["id"] == "test-2"
        finally:
            with rag._conn() as conn:
                conn.execute("DROP TABLE IF EXISTS email_chunks_test")
            rag._ready.discard("email_chunks_test")


def live_eval():
    """Ask EVAL_QUESTIONS against real Gmail + Gemini + the index; in-memory chat history only."""
    from langgraph.checkpoint.memory import InMemorySaver

    import agent
    from summarizer import chat_model

    graph = agent.build_graph(chat_model().bind_tools(tools.TOOLS), InMemorySaver())
    print("semantic_search registered:", tools.semantic_search in tools.TOOLS)
    for i, question in enumerate(EVAL_QUESTIONS):
        thread = f"rag-eval-{i}"
        answer = agent.ask(question, thread, graph=graph)
        messages = graph.get_state({"configurable": {"thread_id": thread}}).values["messages"]
        used = [c["name"] for m in messages for c in getattr(m, "tool_calls", [])]
        print(f"\n[{i + 1}] {question}\ntools: {', '.join(used) or '-'}\n{answer}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--live" in sys.argv:
        live_eval()
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn()
        print("ok")
