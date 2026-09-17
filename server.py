import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PUBSUB_TOKEN = os.getenv("PUBSUB_TOKEN")

from flask import Flask, request
import base64
import json

from gmail import get_new_message_ids, get_email_by_id
from summarizer import summarize_email
from state import load_history_id, save_history_id

app = Flask(__name__)

def send_telegram_message(text):
    async def send():
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text
        )

    asyncio.run(send())

@app.route("/pubsub", methods=["POST"])
def pubsub():
    if request.args.get("token") != PUBSUB_TOKEN:
        return "Forbidden", 403

    envelope = request.get_json(silent=True)

    if not envelope or "message" not in envelope:
        return "Bad Request", 400

    message = envelope["message"]

    try:
        data = base64.b64decode(message["data"]).decode("utf-8")
        notification = json.loads(data)
    except Exception as e:
        print(f"Invalid Pub/Sub message: {e}")
        return "Bad Request", 400

    new_history_id = notification.get("historyId")

    if not new_history_id:
        return "No history ID", 200

    previous_history_id = load_history_id()

    print(f"Previous history ID: {previous_history_id}")
    print(f"New history ID: {new_history_id}")

    # First notification establishes the baseline.
    if not previous_history_id:
        save_history_id(new_history_id)
        print("History baseline established.")
        return "OK", 200

    try:
        message_ids = get_new_message_ids(previous_history_id)

        print(f"Found {len(message_ids)} new message(s).")

        for message_id in message_ids:
            try:
                email = get_email_by_id(message_id)

                if email is None:
                    continue

                print(f"New email: {email['subject']}")

                summary = summarize_email(email)

                print(summary)
                send_telegram_message(summary)

            except Exception as e:
                print(f"Could not process message {message_id}: {e}")

    except Exception as e:
        print(f"Could not retrieve Gmail history: {e}")

    # Always acknowledge the Pub/Sub notification.
    save_history_id(new_history_id)

    return "OK", 200


@app.route("/", methods=["GET"])
def health():
    return "Email summarizer is running", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )