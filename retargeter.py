import logging
from datetime import datetime
from typing import List, Dict, Any

from database import Database
from email_sender import EmailSender
from context_generator import ContextGenerator
from config import Config

logger = logging.getLogger(__name__)


class Retargeter:
    def __init__(self, db: Database, sender: EmailSender,
                 context_generator: ContextGenerator,
                 retarget_after_days: int = None,
                 max_attempts: int = None):
        self.db = db
        self.sender = sender
        self.context_generator = context_generator
        self.retarget_after_days = retarget_after_days or Config.RETARGET_AFTER_DAYS
        self.max_attempts = max_attempts or Config.MAX_RETARGET_ATTEMPTS

    def run_retargeting_cycle(self) -> Dict[str, Any]:
        """Find non-responders eligible for retargeting and send follow-up emails."""
        candidates = self.db.get_non_responders_for_retarget(
            after_days=self.retarget_after_days,
            max_attempts=self.max_attempts,
        )
        logger.info(f"Found {len(candidates)} candidates for retargeting")

        retargeted: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for cand in candidates:
            try:
                ctx = self.context_generator.generate(
                    to_email=cand["email_address"],
                    to_name=cand.get("name"),
                    context_tag=cand.get("context_tag", "sales_intro"),
                    company=cand.get("company"),
                    extra_vars=None,
                    is_retarget=True,
                )

                send_res = self.sender.send_email(
                    to_email=cand["email_address"],
                    to_name=cand.get("name"),
                    subject=ctx["subject"],
                    body_html=ctx["body_html"],
                    body_text=ctx["body_text"],
                )

                attempt_number = int(cand.get("attempt_number", 1)) + 1
                new_status = (self.db.EMAIL_STATUS_RETARGETED
                              if send_res["success"] else self.db.EMAIL_STATUS_FAILED)

                self.db.record_email(
                    client_id=cand["client_id"],
                    email_address=cand["email_address"],
                    subject=ctx["subject"],
                    body=ctx["body_html"],
                    status=new_status,
                    error_message=send_res["error"],
                    message_id=send_res["message_id"],
                    attempt_number=attempt_number,
                    is_retarget=1,
                    sent_at=send_res["sent_at"],
                )

                entry = {
                    "email_address": cand["email_address"],
                    "name": cand.get("name"),
                    "company": cand.get("company"),
                    "attempt_number": attempt_number,
                    "success": send_res["success"],
                    "message_id": send_res["message_id"],
                }
                if send_res["success"]:
                    retargeted.append(entry)
                else:
                    entry["error"] = send_res["error"]
                    failed.append(entry)
            except Exception:
                logger.exception(f"Failed retargeting {cand.get('email_address')}")
                failed.append({
                    "email_address": cand.get("email_address"),
                    "name": cand.get("name"),
                    "error": "Exception while sending",
                })

        return {
            "candidates_count": len(candidates),
            "retargeted": retargeted,
            "failed": failed,
            "total_sent": len(retargeted),
            "total_failed": len(failed),
        }
