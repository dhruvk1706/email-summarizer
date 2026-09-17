from gmail import get_latest_emails

emails = get_latest_emails(3)

for i, email in enumerate(emails, 1):
    print("=" * 80)
    print(f"Email {i}")
    print("From   :", email["from"])
    print("Subject:", email["subject"])
    print("Date   :", email["date"])
    print("\nBody:")
    print(email["body"][:1000])  # First 1000 characters