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


def summarize_email(email):
    prompt = f"""
Summarize the following email clearly and concisely.

From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}

Email:
{email['body']}

Return:
1. A one-line summary
2. The key points
3. Any action required from me
4. Any important deadline or date

Do not invent information that is not present in the email.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text