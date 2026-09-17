from summarizer import summarize_emails

emails = [
    {
        "from": "alice@example.com",
        "subject": "Meeting tomorrow",
        "body": "Let's meet tomorrow at 10 AM to discuss the project roadmap."
    }
]

print(summarize_emails(emails))