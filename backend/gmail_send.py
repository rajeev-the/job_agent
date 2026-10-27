import os
import json
import base64
import pickle
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

# Gmail API scope - only sending permission
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
if not os.path.exists(CREDENTIALS_FILE) and os.path.exists("/etc/secrets/credentials.json"):
    CREDENTIALS_FILE = "/etc/secrets/credentials.json"

TOKEN_FILE = os.getenv("TOKEN_FILE", "token.pkl")
if not os.path.exists(TOKEN_FILE) and os.path.exists("/etc/secrets/token.pkl"):
    TOKEN_FILE = "/etc/secrets/token.pkl"

TOKEN_JSON_FILE = os.getenv("TOKEN_JSON_FILE", "token.json")
if not os.path.exists(TOKEN_JSON_FILE) and os.path.exists("/etc/secrets/token.json"):
    TOKEN_JSON_FILE = "/etc/secrets/token.json"


# ─────────────────────────────────────────
# Get Gmail service
# Loads from GMAIL_TOKEN_JSON env, token.json, or token.pkl
# ─────────────────────────────────────────
def get_gmail_service():
    creds = None

    # 1. Check GMAIL_TOKEN_JSON environment variable (recommended for Render/cloud)
    token_json_env = os.getenv("GMAIL_TOKEN_JSON")
    if token_json_env:
        try:
            token_data = json.loads(token_json_env)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            print("Loaded Gmail credentials from GMAIL_TOKEN_JSON env var")
        except Exception as e:
            print(f"Warning: Failed to load GMAIL_TOKEN_JSON: {e}")

    # 2. Check token.json file
    if not creds and os.path.exists(TOKEN_JSON_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_JSON_FILE, SCOPES)
            print(f"Loaded Gmail credentials from {TOKEN_JSON_FILE}")
        except Exception as e:
            print(f"Warning: Failed to load from {TOKEN_JSON_FILE}: {e}")

    # 3. Check GMAIL_TOKEN_B64 env var
    if not creds:
        token_b64 = os.getenv("GMAIL_TOKEN_B64")
        if token_b64:
            try:
                raw_bytes = base64.b64decode(token_b64)
                creds = pickle.loads(raw_bytes)
                print("Loaded Gmail credentials from GMAIL_TOKEN_B64")
            except Exception as e:
                print(f"Warning: Failed to load from GMAIL_TOKEN_B64: {e}")

    # 4. Check token.pkl file (with recovery if text/json was saved into it)
    if not creds and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
            print(f"Loaded Gmail credentials from {TOKEN_FILE}")
        except Exception as pkl_err:
            print(f"Warning: Could not unpickle {TOKEN_FILE}: {pkl_err}. Trying JSON fallback...")
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                    # In case JSON was saved in token.pkl
                    if "{" in content and "}" in content:
                        json_str = content[content.find("{"):content.rfind("}")+1]
                        token_data = json.loads(json_str)
                        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                        print(f"Recovered Gmail credentials from JSON in {TOKEN_FILE}")
            except Exception as json_err:
                print(f"Could not load {TOKEN_FILE} as JSON: {json_err}")

    # 5. Fallback for local initial authorization if credentials.json is present
    if not creds:
        if os.path.exists(CREDENTIALS_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
            try:
                with open(TOKEN_FILE, "wb") as f:
                    pickle.dump(creds, f)
            except Exception:
                pass
        else:
            raise ValueError(
                "No valid Gmail credentials found. Please configure the GMAIL_TOKEN_JSON environment variable."
            )

    # Refresh expired access token
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("Refreshing expired Gmail access token...")
            creds.refresh(Request())
            print("Gmail token refreshed successfully.")
        else:
            raise ValueError("Gmail credentials expired and cannot be refreshed (no refresh token).")

    service = build('gmail', 'v1', credentials=creds)
    return service


# ─────────────────────────────────────────
# Build email with attachment
# ─────────────────────────────────────────
def build_email(to: str, subject: str, body: str, resume_path: str) -> str:
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = os.getenv("GMAIL_ADDRESS")
    message['subject'] = subject

    # Add email body
    import re
    body_formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body)

    paragraphs = body_formatted.split('\n\n')
    html_paragraphs = ""
    for para in paragraphs:
        para = para.replace('\n', '<br>')
        html_paragraphs += f'<p style="margin: 0 0 18px 0; text-align: left;">{para}</p>'

    html_body = f"""<html>
    <body style="font-family: Arial, sans-serif; font-size: 15px; line-height: 1.7; color: #222222; margin: 0; padding: 0;">
    <div style="padding: 10px 0;">
    {html_paragraphs}
    </div>
    </body>
    </html>"""
    message.attach(MIMEText(html_body, 'html'))

    # Attach resume PDF
    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(resume_path)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={filename}'
            )
            message.attach(part)
        print(f"✅ Resume attached: {filename}")
    else:
        print("⚠️ No resume attached - file not found")

    # Encode to base64 for Gmail API
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw


# ─────────────────────────────────────────
# Send email
# ─────────────────────────────────────────
def send_email(
    to: str,
    subject: str,
    body: str,
    resume_path: str
) -> dict:
    try:
        service = get_gmail_service()

        raw_message = build_email(to, subject, body, resume_path)

        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()

        print(f"✅ Email sent successfully!")
        print(f"Message ID: {sent['id']}")

        return {
            "success": True,
            "message_id": sent['id'],
            "sent_to": to
        }

    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# ─────────────────────────────────────────
# TEST
# ─────────────────────────────────────────
# if __name__ == "__main__":

#     print("=" * 40)
#     print("Testing Gmail Send")
#     print("=" * 40)

#     # Test email - sending to yourself first to verify
#     test_to = os.getenv("GMAIL_ADDRESS")  # sends to yourself
#     test_subject = "Test - Job Agent Email"
#     test_body = """Dear Hiring Team,

# This is a test email from my Job Agent app.

# Kind regards,
# Manikandan M"""

#     # Use any resume from your resumes folder
#     test_resume = "resumes/Res_Fullstack.pdf"

#     print(f"Sending test email to: {test_to}")
#     print("A browser will open first time for Google permission...")
#     print()

#     result = send_email(
#         to=test_to,
#         subject=test_subject,
#         body=test_body,
#         resume_path=test_resume
#     )

#     print()
#     if result["success"]:
#         print("✅ Check your Gmail inbox!")
#     else:
#         print(f"❌ Error: {result['error']}")