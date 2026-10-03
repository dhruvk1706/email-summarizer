"""Draft-generation API contract checks with a mocked Vertex client; no network.

Run: python test_drafting.py
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import agent
import server
import summarizer
import tools


class DraftingTests(unittest.TestCase):
    def test_uses_existing_client_and_model_with_structured_output(self):
        with patch.object(summarizer.client.models, "generate_content", return_value=SimpleNamespace(
            text=json.dumps({"subject": " Sending\nit tomorrow ", "body": " Hi John,\n\nI'll send it tomorrow. "}),
        )) as generate:
            draft = summarizer.generate_email_draft("John", "Say I'll send it tomorrow.", "Reference email")
        self.assertEqual(draft, {"subject": "Sending it tomorrow", "body": "Hi John,\n\nI'll send it tomorrow."})
        request = generate.call_args.kwargs
        self.assertEqual(request["model"], "gemini-2.5-flash")
        self.assertEqual(json.loads(request["contents"]), {
            "recipient": "John", "instructions": "Say I'll send it tomorrow.", "context": "Reference email",
        })
        self.assertEqual(request["config"]["response_mime_type"], "application/json")
        self.assertEqual(request["config"]["response_schema"]["required"], ["subject", "body"])

    def test_invalid_or_incomplete_output_is_rejected(self):
        for text in (None, "", "not JSON", "null", "[]", "{}", '{"subject":"Hi","body":""}',
                     '{"subject":3,"body":"Hi"}', '{"subject":"Hi","body":"  "}'):
            with self.subTest(text=text), patch.object(
                summarizer.client.models, "generate_content", return_value=SimpleNamespace(text=text),
            ):
                with self.assertRaises(ValueError):
                    summarizer.generate_email_draft("John", "Say hello.")

    def test_missing_recipient_or_instructions_never_calls_vertex(self):
        with patch.object(tools, "generate_email_draft") as generate:
            for recipient, instructions in (("", "Hi"), ("John", " ")):
                with self.subTest(recipient=recipient), self.assertRaises(ValueError):
                    tools.draft_email.invoke({"recipient": recipient, "instructions": instructions})
            generate.assert_not_called()

    def test_recipient_header_stays_on_one_line(self):
        with patch.object(tools, "generate_email_draft", return_value={"subject": "Hi", "body": "Hello"}):
            preview = tools.draft_email.invoke({"recipient": " John\n Doe ", "instructions": "Say hello"})
        self.assertIn("To: John Doe\nSubject: Hi", preview)

    def test_webhook_graph_vertex_and_telegram_preview(self):
        prompts = []

        def invoke(messages):
            prompts.append(messages)
            return AIMessage("", tool_calls=[{
                "name": "draft_email", "id": "draft-call", "args": {
                    "recipient": "John", "instructions": "Say I'll send it tomorrow.",
                },
            }])

        graph = agent.build_graph(SimpleNamespace(invoke=invoke), InMemorySaver())
        with patch.object(server, "TELEGRAM_CHAT_ID", "555"), \
             patch.object(server, "TELEGRAM_WEBHOOK_SECRET", "test-secret"), \
             patch.object(agent, "_get_graph", return_value=graph), \
             patch.object(summarizer.client.models, "generate_content", return_value=SimpleNamespace(
                 text=json.dumps({"subject": "Sending it tomorrow", "body": "Hi John,\n\nI'll send it tomorrow."}),
             )) as generate, \
             patch.object(server, "send_telegram_message", return_value=101) as send, \
             patch.object(server, "record_sent_message") as record:
            response = server.app.test_client().post("/telegram-webhook", json={"message": {
                "message_id": 100, "chat": {"id": 555},
                "text": "draft an email to John saying I'll send it tomorrow",
            }}, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(prompts), 1)
        generate.assert_called_once()
        send.assert_called_once_with(
            "Email draft (preview only - not sent)\n\nTo: John\nSubject: Sending it tomorrow\n\n"
            "Body:\nHi John,\n\nI'll send it tomorrow.\n\nNot sent or saved to Gmail.",
            reply_to_message_id=100,
        )
        record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
