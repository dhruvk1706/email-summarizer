import asyncio

from gmail import get_latest_emails
from summarizer import summarize_emails

import os
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def main():
    print("Reading emails...")

    emails = get_latest_emails(5)

    print("Summarizing...")

    summary = summarize_emails(emails)

    print(summary)

    bot = Bot(token=TOKEN)

    await bot.send_message(
        chat_id=CHAT_ID,
        text=summary
    )

    print("Sent to Telegram!")


asyncio.run(main())