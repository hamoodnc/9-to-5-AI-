from pathlib import Path
import base64
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailService:
    def __init__(self):
        self.service = None

    def connect(self):
        credentials_path = (
            Path(__file__).parent / "credentials" / "gmail_oauth.json"
        )

        token_path = (
            Path(__file__).parent / "credentials" / "gmail_token.json"
        )

        credentials = None

        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                token_path,
                SCOPES,
            )

        if not credentials or not credentials.valid:
            if (
                credentials
                and credentials.expired
                and credentials.refresh_token
            ):
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path,
                    SCOPES,
                )

                credentials = flow.run_local_server(port=0)

            token_path.write_text(credentials.to_json())

        self.service = build(
            "gmail",
            "v1",
            credentials=credentials,
        )

        return self.service

    def read_emails(self, max_results=5):
        if not self.service:
            self.connect()

        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                maxResults=max_results,
            )
            .execute()
        )

        messages = results.get("messages", [])
        emails = []

        for message in messages:
            msg = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=message["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )

            headers = msg.get("payload", {}).get("headers", [])

            email_data = {
                "id": message["id"],
                "from": "",
                "subject": "",
                "date": "",
                "snippet": msg.get("snippet", ""),
            }

            for header in headers:
                name = header.get("name")

                if name == "From":
                    email_data["from"] = header.get("value", "")
                elif name == "Subject":
                    email_data["subject"] = header.get("value", "")
                elif name == "Date":
                    email_data["date"] = header.get("value", "")

            emails.append(email_data)

        return emails

    def create_draft(self, to, subject, body):
        if not self.service:
            self.connect()

        message = EmailMessage()
        message.set_content(body)

        message["To"] = to
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        draft_body = {
            "message": {
                "raw": encoded_message
            }
        }

        draft = (
            self.service.users()
            .drafts()
            .create(
                userId="me",
                body=draft_body,
            )
            .execute()
        )

        return {
            "status": "draft_created",
            "draft_id": draft["id"],
            "to": to,
            "subject": subject,
        }

    def send_email(self):
        pass