import os
from dotenv import load_dotenv
from google import genai
from google.genai.types import HttpOptions

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION"),
    http_options=HttpOptions(api_version="v1"),
)


def summarize_emails(emails):
    prompt = "Summarize these emails into a concise daily digest.\n\n"

    for i, email in enumerate(emails, 1):
        prompt += f"""
Email {i}
From: {email['from']}
Subject: {email['subject']}

Body:
{email['body']}

"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text