import smtplib
import uuid
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from typing import Dict, Any, Optional, Tuple

from config import Config

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, smtp_host: str = None, smtp_port: int = None,
                 username: str = None, password: str = None, from_name: str = None):
        self.smtp_host = smtp_host or Config.SMTP_HOST
        self.smtp_port = smtp_port or Config.SMTP_PORT
        self.username = username or Config.EMAIL_USERNAME
        self.password = password or Config.EMAIL_PASSWORD
        self.from_name = from_name or Config.EMAIL_FROM_NAME or self.username

    def _get_from_header(self) -> str:
        return formataddr((self.from_name, self.username))

    def _build_message(self, to_email: str, to_name: Optional[str],
                       subject: str, body_html: str, body_text: str = None,
                       headers: Dict[str, str] = None) -> Tuple[MIMEMultipart, str]:
        msg = MIMEMultipart("alternative")
        msg_id = make_msgid()
        msg["Message-ID"] = msg_id
        msg["From"] = self._get_from_header()
        msg["To"] = formataddr((to_name or "", to_email))
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["X-Mailer"] = "EmailAutomationAgent/1.0"

        if headers:
            for k, v in headers.items():
                msg[k] = v

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg, msg_id

    def send_email(self, to_email: str, to_name: Optional[str],
                   subject: str, body_html: str, body_text: str = None,
                   in_reply_to: str = None, references: str = None,
                   headers: Dict[str, str] = None) -> Dict[str, Any]:
        result = {
            "success": False,
            "error": None,
            "message_id": None,
            "sent_at": None,
        }

        try:
            msg, msg_id = self._build_message(to_email, to_name, subject,
                                              body_html, body_text, headers)
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
            if references:
                msg["References"] = references

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, [to_email], msg.as_string())

            result["success"] = True
            result["message_id"] = msg_id
            result["sent_at"] = datetime.now()
            logger.info(f"Email sent successfully to {to_email} (Message-ID: {msg_id})")
        except smtplib.SMTPAuthenticationError as e:
            result["error"] = f"Authentication failed: {str(e)}"
            logger.error(f"SMTP auth error for {to_email}: {e}")
        except smtplib.SMTPRecipientsRefused as e:
            result["error"] = f"Recipient refused: {str(e)}"
            logger.error(f"Recipient refused {to_email}: {e}")
        except smtplib.SMTPException as e:
            result["error"] = f"SMTP error: {str(e)}"
            logger.error(f"SMTP error sending to {to_email}: {e}")
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.exception(f"Failed sending to {to_email}")

        return result

    def send_batch(self, recipients: list) -> Dict[str, Any]:
        """
        recipients: list of dicts with keys: to_email, to_name, subject, body_html, body_text
        Returns: { "results": [...], "failed_emails": [...] }
        """
        results = []
        failed = []

        for rec in recipients:
            res = self.send_email(
                to_email=rec["to_email"],
                to_name=rec.get("to_name"),
                subject=rec["subject"],
                body_html=rec["body_html"],
                body_text=rec.get("body_text"),
                in_reply_to=rec.get("in_reply_to"),
                references=rec.get("references"),
                headers=rec.get("headers"),
            )
            res.update(rec)
            results.append(res)
            if not res["success"]:
                failed.append({
                    "email": rec["to_email"],
                    "name": rec.get("to_name"),
                    "error": res["error"],
                })

        return {"results": results, "failed_emails": failed}
