from app.services.gmail_service import send_email


def main():
    recipient = input("Enter recipient Gmail address: ").strip()

    result = send_email(
        to_email=recipient,
        subject="LeadFlow AI - Gmail Integration Test",
        body="Gmail integration test successful.",
    )

    print(result)


if __name__ == "__main__":
    main()