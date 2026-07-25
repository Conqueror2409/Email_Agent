import imaplib
import email
import logging
import re
from email.header import decode_header, make_header
from email.message import Message
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dateutil import parser as date_parser

from config import Config
from database import Database

logger = logging.getLogger(__name__)

ACKNOWLEDGMENT_PATTERNS = [
    re.compile(r"\b(thanks?|thank you|thx|tx|appreciate)\b", re.I),
    re.compile(r"\b(ack|acknowledged|got it|received|noted)\b", re.I),
    re.compile(r"\b(will get back|look into|check and revert)\b", re.I),
]


def _decode(s) -> str:
    if s is None:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


def _extract_body(msg: Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, errors="ignore")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="ignore") if payload else ""
        except Exception:
            body = ""
    return body.strip()


def _is_acknowledgment_only(body: str, subject: str) -> bool:
    text = f"{subject}\n{body}"
    text_short = text[:1500]
    word_count = len(re.findall(r"\b\w+\b", text_short))
    has_ack = any(p.search(text_short) for p in ACKNOWLEDGMENT_PATTERNS)
    if has_ack and word_count < 60:
        return True
    return False


def _clean_message_id(msg_id: Optional[str]) -> str:
    if not msg_id:
        return ""
    return msg_id.strip().replace("\r", "").replace("\n", "")


class ReplyTracker:
    def __init__(self, db: Database, imap_host: str = None, imap_port: int = None,
                 username: str = None, password: str = None):
        self.db = db
        self.imap_host = imap_host or Config.IMAP_HOST
        self.imap_port = imap_port or Config.IMAP_PORT
        self.username = username or Config.EMAIL_USERNAME
        self.password = password or Config.EMAIL_PASSWORD

    def check_for_replies(self, since_days: int = 14,
                          folder: str = "INBOX") -> List[Dict[str, Any]]:
        new_replies: List[Dict[str, Any]] = []
        if not self.username or not self.password:
            logger.warning("Email credentials not set; skipping reply check.")
            return new_replies

        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as imap:
                imap.login(self.username, self.password)
                status, _ = imap.select(folder, readonly=True)
                if status != "OK":
                    logger.error(f"Could not select folder {folder}")
                    return new_replies

                since_date = (datetime.now() - timedelta(days=since_days))\
                    .strftime("%d-%b-%Y")
                status, data = imap.search(None, f'(SINCE "{since_date}")')
                if status != "OK" or not data or not data[0]:
                    logger.info("No messages found in search")
                    return new_replies

                msg_ids = data[0].split()
                logger.info(f"Checking {len(msg_ids)} messages for replies")

                for mid in msg_ids:
                    try:
                        status, msg_data = imap.fetch(mid, "(RFC822)")
                        if status != "OK" or not msg_data or not msg_data[0]:
                            continue
                        raw = msg_data[0][1]
                        parsed = email.message_from_bytes(raw)

                        reply_message_id = _clean_message_id(parsed.get("Message-ID"))
                        if not reply_message_id:
                            continue
                        if self.db.reply_exists(reply_message_id):
                            continue

                        in_reply_to = _clean_message_id(parsed.get("In-Reply-To"))
                        references = _clean_message_id(parsed.get("References") or "")
                        # If In-Reply-To not set, split References (space-separated) and take last
                        effective_in_reply_to = in_reply_to
                        if not effective_in_reply_to and references:
                            refs = [r for r in references.split() if r]
                            if refs:
                                effective_in_reply_to = refs[-1]

                        from_raw = parsed.get("From", "")
                        from_addr = self._extract_email(from_raw)
                        subject = _decode(parsed.get("Subject", ""))
                        body = _extract_body(parsed)

                        date_raw = parsed.get("Date", "")
                        try:
                            replied_at = date_parser.parse(date_raw)
                            if replied_at.tzinfo is None:
                                replied_at = replied_at.replace(tzinfo=timezone.utc)
                        except Exception:
                            replied_at = datetime.now(timezone.utc)

                        is_ack = 0 if not _is_acknowledgment_only(body, subject) else 1

                        reply_id = self.db.record_reply(
                            from_address=from_addr,
                            subject=subject,
                            body=body[:8000],
                            reply_message_id=reply_message_id,
                            in_reply_to=effective_in_reply_to,
                            replied_at=replied_at,
                            is_acknowledgment=is_ack,
                        )

                        new_replies.append({
                            "id": reply_id,
                            "from_address": from_addr,
                            "subject": subject,
                            "body": body[:500],
                            "replied_at": replied_at.isoformat(),
                            "is_acknowledgment": is_ack,
                            "in_reply_to": effective_in_reply_to,
                        })
                    except Exception as e:
                        logger.exception(f"Error processing message {mid}")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
        except Exception:
            logger.exception("Unexpected error in reply check")

        logger.info(f"Detected {len(new_replies)} new replies")
        return new_replies

    @staticmethod
    def _extract_email(from_header: str) -> str:
        if not from_header:
            return ""
        m = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", from_header)
        return m.group(0) if m else from_header
