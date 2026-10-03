"""Webhook dispatch checks; no network. Run: python test_webhook.py"""

from unittest.mock import patch

import server

server.TELEGRAM_CHAT_ID = "555"
server.TELEGRAM_WEBHOOK_SECRET = "s3cret"
client = server.app.test_client()
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}

sent, recorded, asked = [], [], []
server.send_telegram_message = lambda text, reply_to_message_id=None: (sent.append(text), len(sent))[1]
server.record_sent_message = lambda message_id, email_id: recorded.append((message_id, email_id))
server.get_uid_for_message = lambda message_id: "111" if message_id == 7 else None
server.agent.ask = lambda text, thread_id, email_id=None: (asked.append((text, thread_id, email_id)), "answer")[1]


def post(message, headers=HEADERS):
    for log in (sent, recorded, asked):
        log.clear()
    return client.post("/telegram-webhook", json={"message": message}, headers=headers)


def msg(text, chat=555, **extra):
    return {"message_id": 100, "chat": {"id": chat}, "text": text, **extra}


def test_bad_secret_rejected():
    assert post(msg("hi"), headers={}).status_code == 403 and not asked


def test_other_chat_ignored():
    assert post(msg("read my mail", chat=999)).status_code == 200 and not asked and not sent


def test_plain_message_goes_to_agent():
    post(msg("what are my latest emails?"))
    assert asked == [("what are my latest emails?", "555", None)] and sent == ["answer"] and not recorded


def test_reply_passes_email_context():
    post(msg("when is the meeting?", reply_to_message={"message_id": 7}))
    assert asked[0][2] == "111" and recorded == [(1, "111")]


def test_draft_request_uses_normal_dispatch():
    post(msg("draft an email to John saying I'll send it tomorrow"))
    assert asked == [("draft an email to John saying I'll send it tomorrow", "555", None)]
    assert sent == ["answer"] and not recorded


def test_draft_reply_keeps_email_context():
    post(msg("draft a reply saying I'll send it tomorrow", reply_to_message={"message_id": 7}))
    assert asked[0][2] == "111" and recorded == [(1, "111")]


def test_draft_preview_is_delivered_and_chunked_verbatim():
    preview = "Email draft (preview only - not sent)\n\nTo: John\nSubject: Report\n\nBody:\n" + "x" * 4100
    with patch.object(server.agent, "ask", return_value=preview):
        post(msg("draft an email to John about the report", reply_to_message={"message_id": 7}))
    assert "".join(sent) == preview and all(len(s) <= server.TELEGRAM_MAX_LEN for s in sent)
    assert recorded == [(i + 1, "111") for i in range(len(sent))]


def test_poll_still_summarizes_and_records_new_mail():
    email = {"id": "222", "subject": "Report", "body": "Original email"}
    sent.clear()
    recorded.clear()
    with patch.object(server, "POLL_TOKEN", "poll-secret"), \
         patch.object(server, "get_new_emails", return_value=[email]), \
         patch.object(server, "is_delivered", return_value=False), \
         patch.object(server, "summarize_email", return_value="Email summary") as summarize, \
         patch.object(server, "mark_delivered") as delivered, \
         patch.object(server.agent, "ask") as ask:
        assert client.post("/poll?token=poll-secret").status_code == 200
    summarize.assert_called_once_with(email)
    delivered.assert_called_once_with("222")
    ask.assert_not_called()
    assert sent == ["Email summary"] and recorded == [(1, "222")]


def test_long_answer_is_chunked():
    server.agent.ask = lambda *a, **k: "x" * (server.TELEGRAM_MAX_LEN + 10)
    post(msg("full"))
    assert [len(s) for s in sent] == [server.TELEGRAM_MAX_LEN, 10]


def test_agent_error_still_replies():
    def boom(*a, **k):
        raise RuntimeError("vertex down")
    server.agent.ask = boom
    post(msg("hi"))
    assert "went wrong" in sent[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
