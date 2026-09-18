import os
import asyncio
import threading
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_TOKEN = os.getenv("POLL_TOKEN")

from flask import Flask, request

from gmail import get_new_emails
from summarizer import summarize_email
from state import is_delivered, mark_delivered

app = Flask(__name__)
# ponytail: in-process lock only guards a single Gunicorn worker. Fine while
# the Dockerfile runs gunicorn with no --workers flag (defaults to 1); if
# workers are ever added, switch to a file lock or DB-based lock instead.
poll_lock = threading.Lock()

def send_telegram_message(text):
    async def send():
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text
        )

    asyncio.run(send())

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
                send_telegram_message(summary)

                mark_delivered(email["id"])

            except Exception as e:
                print(f"Could not process email {email['id']}: {e}")

        return "OK", 200
    finally:
        poll_lock.release()


@app.route("/", methods=["GET"])
def health():
    return "Email summarizer is running", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )
