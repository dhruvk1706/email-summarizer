r"""
Conversational email agent: LangGraph orchestration only.
Gmail access lives in tools.py/gmail.py, the LLM + prompt in summarizer.py,
Telegram I/O in server.py.

Graph:  START -> agent -(tool calls?)-> tools -> agent ... -> END
                                           \-(show_full_email)-> show_full -> END
                                           \-(draft_email)-> show_draft -> END

Usage (local chat against real Gmail + Gemini): python agent.py
"""

import os
import time

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from summarizer import AGENT_SYSTEM_PROMPT, chat_model
from tools import TOOLS

HISTORY_TURNS = 20
RECURSION_LIMIT = 12
MAX_AGE = 2 * 24 * 3600  # seconds a message lives in memory
GAVE_UP = "Sorry, I couldn't complete that. Could you ask more specifically?"


def _recent(messages):
    # ponytail: only the last N user turns go to the LLM (cut at a user message so
    # tool call/result pairs stay intact); summarize older history if that's too short.
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    return messages[starts[-HISTORY_TURNS]:] if len(starts) > HISTORY_TURNS else messages


def _expired(messages, now):
    # Everything before the first user turn posted within MAX_AGE (cut at a user message so
    # tool call/result pairs stay intact). Turns without a ts (pre-expiry history) count as old.
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage) and now - m.additional_kwargs.get("ts", 0) < MAX_AGE:
            return messages[:i]
    return messages


def _last_tool_batch(messages):
    batch = []
    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            break
        batch.append(m)
    return batch[::-1]


def build_graph(model, checkpointer):
    """model: a chat model already bound to TOOLS (injected so tests can script it)."""

    def agent(state):
        prompt = [SystemMessage(AGENT_SYSTEM_PROMPT), *_recent(state["messages"])]
        return {"messages": [model.invoke(prompt)]}

    def after_tools(state):
        batch = _last_tool_batch(state["messages"])
        if any(m.name == "draft_email" and m.status == "success" for m in batch):
            return "show_draft"
        return "show_full" if any(m.name == "show_full_email" for m in batch) else "agent"

    def show_full(state):
        # Verbatim email body straight from Gmail; the LLM never retypes it.
        batch = _last_tool_batch(state["messages"])
        return {"messages": [AIMessage("\n\n".join(m.content for m in batch if m.name == "show_full_email"))]}

    def show_draft(state):
        # Keep the formatted preview intact instead of asking the agent to retype it.
        batch = _last_tool_batch(state["messages"])
        return {"messages": [AIMessage("\n\n".join(
            m.content for m in batch
            if m.name in {"draft_email", "show_full_email"} and m.status == "success"
        ))]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    graph.add_node("show_full", show_full)
    graph.add_node("show_draft", show_draft)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", after_tools, ["agent", "show_full", "show_draft"])
    graph.add_edge("show_full", END)
    graph.add_edge("show_draft", END)
    return graph.compile(checkpointer=checkpointer)


def _checkpointer():
    url = os.getenv("DATABASE_URL")

    if not url:
        print("WARNING: DATABASE_URL not set; conversation memory is in-process only.")
        return InMemorySaver()

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # prepare_threshold=0 keeps it working behind transaction-mode poolers (pgbouncer/Supabase).
    pool = ConnectionPool(
        url,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(chat_model().bind_tools(TOOLS), _checkpointer())
    return _graph


def ask(text, thread_id, email_id=None, graph=None):
    """Run one conversational turn; returns the reply text."""
    graph = graph or _get_graph()
    config = {"configurable": {"thread_id": str(thread_id)}, "recursion_limit": RECURSION_LIMIT}

    # ponytail: lazy purge on the next message, no cron; an unused chat's rows linger in the DB.
    old = _expired(graph.get_state(config).values.get("messages", []), time.time())
    if old:
        graph.update_state(config, {"messages": [RemoveMessage(id=m.id) for m in old]}, as_node="show_full")

    if email_id:
        text = f"[User is replying about email id {email_id}]\n{text}"

    try:
        result = graph.invoke({"messages": [HumanMessage(text, additional_kwargs={"ts": time.time()})]}, config)
    except GraphRecursionError:
        # Close out any dangling tool calls so the saved history stays valid next turn.
        last = graph.get_state(config).values["messages"][-1]
        pending = [ToolMessage("Aborted.", tool_call_id=c["id"]) for c in getattr(last, "tool_calls", [])]
        graph.update_state(config, {"messages": [*pending, AIMessage(GAVE_UP)]}, as_node="show_full")
        return GAVE_UP

    return result["messages"][-1].text


if __name__ == "__main__":
    import uuid

    thread = f"cli-{uuid.uuid4()}"
    print("Email agent chat. Ctrl+C to quit.")

    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text:
            print("\nbot>", ask(text, thread))
