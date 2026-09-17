from gmail import get_gmail_service


def start_gmail_watch(topic_name):
    service = get_gmail_service()

    response = service.users().watch(
        userId="me",
        body={
            "labelIds": ["INBOX"],
            "topicName": topic_name,
        }
    ).execute()

    print("Gmail watch started")
    print("History ID:", response.get("historyId"))
    print("Expiration:", response.get("expiration"))

    return response


if __name__ == "__main__":
    start_gmail_watch(
        "projects/email-assistant-508816/topics/gmail-notifications"
    )