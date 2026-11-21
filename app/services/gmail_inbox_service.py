from googleapiclient.discovery import build

from app.services.gmail_auth import get_gmail_credentials
from app.services.gmail_parser import parse_gmail_message


def get_gmail_service():
    return build(
        "gmail",
        "v1",
        credentials=get_gmail_credentials(),
        cache_discovery=False,
    )


def fetch_gmail_messages(
    max_results: int = 50,
    unread: bool | None = None,
    after_timestamp: int | None = None,
    max_pages: int = 5,
) -> tuple[list[dict], int]:
    service = get_gmail_service()
    query_parts: list[str] = []
    if unread:
        query_parts.append("is:unread")
    if after_timestamp:
        query_parts.append(f"after:{int(after_timestamp)}")

    query = " ".join(query_parts) if query_parts else None
    fetched: list[dict] = []
    page_token: str | None = None

    for _ in range(max(1, max_pages)):
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=min(max_results, 500),
                pageToken=page_token,
                q=query,
            )
            .execute()
        )

        for item in response.get("messages") or []:
            message_id = item.get("id")
            if not message_id:
                continue
            raw = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full",
                )
                .execute()
            )
            parsed = parse_gmail_message(raw)
            if parsed["message_id"]:
                fetched.append(parsed)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return fetched, len(fetched)
