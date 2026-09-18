import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_TOKEN = os.getenv("POLL_TOKEN")

from flask import Flask, request

from gmail import get_new_emails
from summarizer import summarize_email

app = Flask(__name__)

def send_telegram_message(text):
    async def send():
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text
        )

    asyncio.run(send())

@app.route("/poll", methods=["POST", "GET"])
def poll():
    if request.args.get("token") != POLL_TOKEN:
        return "Forbidden", 403

    emails = get_new_emails()

    print(f"Found {len(emails)} new email(s).")

    for email in emails:
        try:
            print(f"New email: {email['subject']}")

            summary = summarize_email(email)

            print(summary)
            send_telegram_message(summary)

        except Exception as e:
            print(f"Could not process email {email['id']}: {e}")

    return "OK", 200


@app.route("/", methods=["GET"])
def health():
    return "Email summarizer is running", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )
