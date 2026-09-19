import server

server.record_sent_message = lambda message_id, uid: None


def test_full_command_sends_body():
    sent = []
    server.send_telegram_message = lambda text, reply_to_message_id=None: (sent.append(text), 1)[1]
    server.get_email_by_uid = lambda uid: {"body": "hello world"}
    server.handle_reply_command("full", "42", 100)
    assert sent == ["hello world"]


def test_full_command_missing_email():
    sent = []
    server.send_telegram_message = lambda text, reply_to_message_id=None: (sent.append(text), 1)[1]
    server.get_email_by_uid = lambda uid: None
    server.handle_reply_command("full", "42", 100)
    assert "not find" in sent[0]


def test_unknown_command():
    sent = []
    server.send_telegram_message = lambda text, reply_to_message_id=None: (sent.append(text), 1)[1]
    server.classify_reply_command = lambda text: None
    server.handle_reply_command("blah", "42", 100)
    assert "Unknown command" in sent[0]


def test_natural_language_full_command():
    sent = []
    server.send_telegram_message = lambda text, reply_to_message_id=None: (sent.append(text), 1)[1]
    server.get_email_by_uid = lambda uid: {"body": "hello world"}
    server.classify_reply_command = lambda text: "full"
    server.handle_reply_command("can I see the full email please", "42", 100)
    assert sent == ["hello world"]


if __name__ == "__main__":
    test_full_command_sends_body()
    test_full_command_missing_email()
    test_unknown_command()
    test_natural_language_full_command()
    print("ok")
