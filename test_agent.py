"""Conversational-flow checks with a scripted fake model; no network. Run: python test_agent.py"""

import itertools

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

import agent
import gmail

EMAIL = {
    "id": "111", "from": "John <john@x.com>", "to": "me", "date": "Mon, 1 Sep 2026",
    "subject": "Report", "body": "Please send the Q3 report by Friday. Meeting Thursday 3pm.",
}
gmail.search_emails = lambda q, n: [{**EMAIL, "snippet": EMAIL["body"][:20]}] if "john" in q else []
gmail.get_email_by_id = lambda i: EMAIL if i == "111" else None


class FakeModel:
    """Returns scripted replies in order and records every prompt it sees."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, messages):
        self.prompts.append(messages)
        return self.replies.pop(0)


_ids = itertools.count()


def call(name, **args):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call{next(_ids)}"}])


def new(model):
    return agent.build_graph(model, InMemorySaver())


def test_search_then_grounded_answer():
    model = FakeModel(call("search_emails", query="from:john"), AIMessage("John wants the Q3 report by Friday."))
    reply = agent.ask("what did John ask me to do?", "t1", graph=new(model))
    assert reply == "John wants the Q3 report by Friday."
    tool_result = model.prompts[1][-1]
    assert isinstance(tool_result, ToolMessage) and "id: 111" in tool_result.content


def test_full_email_is_verbatim_and_skips_llm():
    model = FakeModel(call("show_full_email", email_id="111"))
    reply = agent.ask("give me the complete email", "t2", email_id="111", graph=new(model))
    assert EMAIL["body"] in reply and len(model.prompts) == 1
    assert "replying about email id 111" in model.prompts[0][-1].content


def test_multi_turn_follow_up_sees_history():
    model = FakeModel(
        call("get_email", email_id="111"), AIMessage("It's about the Q3 report."),
        AIMessage("The meeting is Thursday at 3pm."),
    )
    graph = new(model)
    agent.ask("what is this email about?", "t3", email_id="111", graph=graph)
    reply = agent.ask("when is the meeting?", "t3", graph=graph)
    assert reply == "The meeting is Thursday at 3pm."
    history = model.prompts[-1]
    assert any(isinstance(m, ToolMessage) and "Thursday 3pm" in m.content for m in history)
    assert [m.content for m in history if isinstance(m, HumanMessage)][-1] == "when is the meeting?"


def test_not_found_is_reported_to_model():
    model = FakeModel(call("get_email", email_id="999"), AIMessage("I can't find that email."))
    agent.ask("show email 999", "t4", graph=new(model))
    assert "No email found" in model.prompts[1][-1].content


def test_tool_error_does_not_crash():
    def boom(i):
        raise ConnectionError("imap down")
    orig, gmail.get_email_by_id = gmail.get_email_by_id, boom
    try:
        model = FakeModel(call("get_email", email_id="111"), AIMessage("I couldn't reach Gmail."))
        assert agent.ask("read it", "t5", graph=new(model)) == "I couldn't reach Gmail."
        assert model.prompts[1][-1].status == "error"
    finally:
        gmail.get_email_by_id = orig


def test_recursion_limit_leaves_valid_history():
    model = FakeModel(*[call("search_emails", query="x") for _ in range(20)], AIMessage("ok"))
    graph = new(model)
    assert agent.ask("loop forever", "t6", graph=graph) == agent.GAVE_UP
    msgs = graph.get_state({"configurable": {"thread_id": "t6"}}).values["messages"]
    called = {c["id"] for m in msgs if isinstance(m, AIMessage) for c in m.tool_calls}
    answered = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    assert called <= answered and msgs[-1].content == agent.GAVE_UP


def test_history_window_cuts_at_user_turn():
    msgs = []
    for i in range(agent.HISTORY_TURNS + 5):
        msgs += [HumanMessage(f"q{i}"), AIMessage(f"a{i}")]
    recent = agent._recent(msgs)
    assert isinstance(recent[0], HumanMessage) and len(recent) == agent.HISTORY_TURNS * 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
