"""Read-only Gmail tools for the agent. Nothing here sends, deletes, or modifies mail."""

from langchain_core.tools import tool

import gmail

MAX_BODY_CHARS = 30000


def _header(e):
    return f"id: {e['id']}\nFrom: {e['from']}\nTo: {e['to']}\nDate: {e['date']}\nSubject: {e['subject']}"


@tool
def search_emails(query: str, max_results: int = 10) -> str:
    """Search the user's mailbox (all mail, newest first) with Gmail search syntax,
    e.g. 'from:john newer_than:30d' or 'subject:invoice'. Empty query = latest emails.
    Returns ids, headers and short snippets; use get_email for full details."""
    results = gmail.search_emails(query, max(1, min(max_results, 20)))

    if not results:
        return f"No emails found for query: {query!r}"

    return "\n\n".join(
        f"{_header(e)}\nPreview (first 300 chars only, cut off; call get_email for the real content): {e['snippet']}"
        for e in results
    )


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


TOOLS = [search_emails, get_email, show_full_email]
