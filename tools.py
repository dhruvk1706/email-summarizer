"""Read-only Gmail and draft-preview tools. Nothing here sends or modifies mail."""

import os

from langchain_core.tools import tool

import gmail
import rag
from summarizer import generate_email_draft

MAX_BODY_CHARS = 30000


def _header(e):
    return f"id: {e['id']}\nFrom: {e['from']}\nTo: {e['to']}\nDate: {e['date']}\nSubject: {e['subject']}"


def _format_results(results, query):
    if not results:
        return f"No emails found for query: {query!r}"

    return "\n\n".join(
        f"{_header(e)}\nPreview (first 300 chars only, cut off; call get_email for the real content): {e['snippet']}"
        for e in results
    )


@tool
def search_emails(query: str, max_results: int = 10) -> str:
    """Search the user's mailbox (all mail, newest first) with Gmail search syntax,
    e.g. 'from:john newer_than:30d' or 'subject:invoice'. Empty query = latest emails.
    Returns ids, headers and short snippets; use get_email for full details."""
    return _format_results(gmail.search_emails(query, max(1, min(max_results, 20))), query)


@tool
def semantic_search(query: str, max_results: int = 10) -> str:
    """Search indexed mail by meaning, not keywords, e.g. 'someone asking me to approve
    a budget' or 'travel plans for next month'. Plain language, not Gmail syntax.
    Returns ids, headers and short snippets of the best-matching emails; use get_email
    for full details."""
    return _format_results(rag.semantic_search(query, max(1, min(max_results, 20))), query)


@tool
def get_email(email_id: str) -> str:
    """Fetch one email's headers and full body by id, to read and answer questions about it."""
    e = gmail.get_email_by_id(email_id)

    if e is None:
        return f"No email found with id {email_id}."

    body = e["body"] or "(empty body)"

    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n[...truncated]"

    return f"{_header(e)}\n\n<email_content>\n{body}\n</email_content>"


@tool
def show_full_email(email_id: str) -> str:
    """Show the user the complete original email verbatim. Use when they ask for the
    full/complete/whole email. The result is sent to the user as-is."""
    e = gmail.get_email_by_id(email_id)

    if e is None:
        return f"Could not find that email (id {email_id}); it may have been deleted."

    return f"From: {e['from']}\nDate: {e['date']}\nSubject: {e['subject']}\n\n{e['body'] or '(empty body)'}"


@tool
def draft_email(recipient: str, instructions: str, context: str = "") -> str:
    """Compose an email draft preview, never send or save it. Recipient can be a
    name or an address supplied by the user. Instructions describe what to say
    and the desired tone. Optional context is retrieved email text or a previous
    draft for replies/revisions. The formatted result is shown to the user as-is."""
    recipient = " ".join(recipient.split())
    instructions = instructions.strip()
    if not recipient or not instructions:
        raise ValueError("Drafting needs a recipient and instructions describing what to say.")
    draft = generate_email_draft(recipient, instructions, context)
    return (
        f"Email draft (preview only - not sent)\n\n"
        f"To: {recipient}\nSubject: {draft['subject']}\n\n"
        f"Body:\n{draft['body']}\n\n"
        "Not sent or saved to Gmail."
    )


TOOLS = [search_emails, get_email, show_full_email, draft_email]

# The index lives in Postgres; without DATABASE_URL there is nothing to search.
if os.getenv("DATABASE_URL"):
    TOOLS.append(semantic_search)
