import os
import sys
import asyncio
import threading
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import BadRequest

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_TOKEN = os.getenv("POLL_TOKEN")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

from flask import Flask, request

import agent
from gmail import get_new_emails
from summarizer import summarize_email
from state import (
    is_delivered,
    mark_delivered,
    record_sent_message,
    get_uid_for_message,
)

TELEGRAM_MAX_LEN = 4096

app = Flask(__name__)
# ponytail: in-process lock only guards a single Gunicorn worker. Fine while
# the Dockerfile runs gunicorn with no --workers flag (defaults to 1); if
# workers are ever added, switch to a file lock or DB-based lock instead.
poll_lock = threading.Lock()

def send_telegram_message(text, reply_to_message_id=None):
    async def send():
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        try:
            msg = await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
        except BadRequest:
            # ponytail: reply target can go stale (deleted/out of range); fall back
            # to an unthreaded send rather than failing the whole request.
            if reply_to_message_id is None:
                raise
            msg = await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        return msg.message_id

    return asyncio.run(send())


def send_long_message(text, reply_to_message_id, email_id=None):
    """Send text in Telegram-sized chunks; map each chunk to email_id so replies keep context."""
    text = text or "(empty reply)"

    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        message_id = send_telegram_message(
            text[i:i + TELEGRAM_MAX_LEN], reply_to_message_id=reply_to_message_id
        )
        if email_id:
            record_sent_message(message_id, email_id)

@app.route("/poll", methods=["POST"])
def poll():
    if request.args.get("token") != POLL_TOKEN:
        return "Forbidden", 403

    if not poll_lock.acquire(blocking=False):
        return "Poll already in progress", 409

    try:
        emails = get_new_emails()

        print(f"Found {len(emails)} new email(s).")

        for email in emails:
            try:
                if is_delivered(email["id"]):
                    continue

                print(f"New email: {email['subject']}")

                summary = summarize_email(email)
                message_id = send_telegram_message(summary)
                record_sent_message(message_id, email["id"])

                mark_delivered(email["id"])

            except Exception as e:
                print(f"Could not process email {email['id']}: {e}")

        return "OK", 200
    finally:
        poll_lock.release()


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_WEBHOOK_SECRET:
        return "Forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id"))
    reply_to = message.get("reply_to_message")
    text = (message.get("text") or "").strip()

    # The agent can read the whole mailbox: only the owner's chat may talk to it.
    # Returns 200 so Telegram doesn't retry messages from strangers.
    if not TELEGRAM_CHAT_ID or chat_id != str(TELEGRAM_CHAT_ID):
        print("Webhook ignored: message from an unauthorized chat.")
        return "OK", 200

    if not text:
        return "OK", 200

    email_id = get_uid_for_message(reply_to["message_id"]) if reply_to else None
    print(f"Webhook dispatch: email_id={email_id} len(text)={len(text)}")

    try:
        reply = agent.ask(text, thread_id=chat_id, email_id=email_id)
    except Exception as e:
        print(f"Agent error: {e!r}")
        reply = "Sorry, something went wrong answering that. Please try again."

    send_long_message(reply, message["message_id"], email_id)
    return "OK", 200


@app.route("/", methods=["GET"])
def health():
    return "Email summarizer is running", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )
