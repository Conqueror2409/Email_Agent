import json
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

from config import Config
from database import Database
from email_sender import EmailSender
from context_generator import ContextGenerator
from slack_notifier import SlackNotifier
from reply_tracker import ReplyTracker
from retargeter import Retargeter

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class EmailAgent:
    def __init__(self, db_path: str = None, sender_name: str = None,
                 our_company: str = None):
        self.db = Database(db_path or Config.DB_PATH)
        self.sender = EmailSender()
        self.context_generator = ContextGenerator(
            sender_name=sender_name or Config.EMAIL_FROM_NAME or Config.EMAIL_USERNAME,
            our_company=our_company or "Our Company",
        )
        self.slack = SlackNotifier()
        self.reply_tracker = ReplyTracker(self.db)
        self.retargeter = Retargeter(self.db, self.sender, self.context_generator)

    # ---------- Validation ----------

    def validate(self) -> List[str]:
        errors = []
        errors.extend(Config.validate_email_config())
        return errors

    # ---------- Importing recipients ----------

    @staticmethod
    def load_recipients_from_csv(path: str) -> List[Dict[str, Any]]:
        df = pd.read_csv(path)
        required = {"email"}
        cols = set(df.columns.str.lower())
        if not required & cols:
            raise ValueError(f"CSV must contain column: {', '.join(required)}")
        rename = {}
        if "email" not in df.columns and "Email" in df.columns:
            rename["Email"] = "email"
        if "name" not in df.columns and "Name" in df.columns:
            rename["Name"] = "name"
        if "company" not in df.columns and "Company" in df.columns:
            rename["Company"] = "company"
        if "context_tag" not in df.columns and "Context" in df.columns:
            rename["Context"] = "context_tag"
        if rename:
            df = df.rename(columns=rename)
        records = df.where(pd.notnull(df), None).to_dict(orient="records")
        return [
            {
                "to_email": r.get("email"),
                "to_name": r.get("name"),
                "company": r.get("company"),
                "context_tag": r.get("context_tag"),
                "extra_vars": {
                    k: v for k, v in r.items()
                    if k not in {"email", "name", "company", "context_tag",
                                  "to_email", "to_name"} and v is not None
                }
            }
            for r in records if r.get("email")
        ]

    @staticmethod
    def load_recipients_from_json(path: str) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for r in data:
            to_email = r.get("email") or r.get("to_email")
            if not to_email:
                continue
            out.append({
                "to_email": to_email,
                "to_name": r.get("name") or r.get("to_name"),
                "company": r.get("company"),
                "context_tag": r.get("context_tag") or r.get("context"),
                "extra_vars": r.get("extra_vars") or {},
            })
        return out

    # ---------- Sending campaign ----------

    def send_campaign(self, recipients: List[Dict[str, Any]],
                      notify_slack: bool = True) -> Dict[str, Any]:
        errors = self.validate()
        if errors:
            raise RuntimeError(f"Configuration errors: {'; '.join(errors)}")

        # Upsert clients and render contexts
        prepared = []
        for rec in recipients:
            client_id = self.db.upsert_client(
                email=rec["to_email"],
                name=rec.get("to_name"),
                company=rec.get("company"),
                context_tag=rec.get("context_tag"),
                extra_data=(json.dumps(rec.get("extra_vars"), default=str)
                            if rec.get("extra_vars") else None),
            )
            rec["_client_id"] = client_id
            prepared.append(rec)

        rendered = self.context_generator.generate_batch(prepared)

        send_payload = [
            {
                "to_email": r["to_email"],
                "to_name": r.get("to_name"),
                "subject": r["subject"],
                "body_html": r["body_html"],
                "body_text": r["body_text"],
                "_client_id": r.get("_client_id"),
            }
            for r in rendered
        ]

        batch_res = self.sender.send_batch(send_payload)

        failed_emails: List[Dict[str, Any]] = []
        total_sent = 0

        for res in batch_res["results"]:
            client_id = res.get("_client_id")
            status = (self.db.EMAIL_STATUS_SENT
                      if res["success"] else self.db.EMAIL_STATUS_FAILED)
            self.db.record_email(
                client_id=client_id,
                email_address=res["to_email"],
                subject=res["subject"],
                body=res["body_html"],
                status=status,
                error_message=res.get("error"),
                message_id=res.get("message_id"),
                attempt_number=1,
                is_retarget=0,
                sent_at=res.get("sent_at"),
            )
            if res["success"]:
                total_sent += 1
            else:
                failed_emails.append({
                    "email": res["to_email"],
                    "name": res.get("to_name"),
                    "error": res.get("error"),
                })

        if notify_slack and self.slack.is_configured():
            self.slack.notify_failed_emails(failed_emails)

        return {
            "total_recipients": len(recipients),
            "sent": total_sent,
            "failed": len(failed_emails),
            "failed_list": failed_emails,
        }

    # ---------- Reply check ----------

    def check_replies(self, since_days: int = 14,
                      notify_slack: bool = True) -> Dict[str, Any]:
        replies = self.reply_tracker.check_for_replies(since_days=since_days)
        if notify_slack and self.slack.is_configured():
            self.slack.notify_responders(replies)
        return {
            "new_replies_count": len(replies),
            "replies": replies,
        }

    # ---------- Non-responder reporting ----------

    def report_non_responders(self, notify_slack: bool = True) -> Dict[str, Any]:
        non_responders = self.db.get_non_responder_details()
        if notify_slack and self.slack.is_configured():
            self.slack.notify_non_responders(non_responders)
        return {
            "count": len(non_responders),
            "non_responders": non_responders,
        }

    # ---------- Retargeting ----------

    def run_retargeting(self, notify_slack: bool = True) -> Dict[str, Any]:
        result = self.retargeter.run_retargeting_cycle()
        if notify_slack and self.slack.is_configured():
            self.slack.notify_retargeting(result["retargeted"])
            if result["failed"]:
                self.slack.notify_failed_emails(result["failed"])
        return result

    # ---------- Summary ----------

    def get_summary(self, notify_slack: bool = False) -> Dict[str, Any]:
        summary = self.db.get_report_summary()
        summary["replies"] = self.db.get_all_replies()
        summary["non_responders"] = self.db.get_non_responder_details()
        summary["failed"] = self.db.get_failed_emails()
        if notify_slack and self.slack.is_configured():
            self.slack.notify_summary(self.db.get_report_summary())
        return summary

    # ---------- Full cycle ----------

    def run_full_cycle(self, recipients: Optional[List[Dict[str, Any]]] = None,
                       send_new: bool = False) -> Dict[str, Any]:
        """
        1. (Optional) Send new campaign.
        2. Check for replies and notify Slack.
        3. Report non-responders to Slack.
        4. Run retargeting and notify Slack.
        5. Return a full summary.
        """
        cycle: Dict[str, Any] = {"started_at": datetime.now().isoformat()}

        if send_new and recipients:
            cycle["campaign"] = self.send_campaign(recipients, notify_slack=True)
        elif send_new:
            logger.warning("send_new=True but no recipients provided.")

        cycle["replies"] = self.check_replies(notify_slack=True)
        cycle["non_responders"] = self.report_non_responders(notify_slack=True)
        cycle["retargeting"] = self.run_retargeting(notify_slack=True)
        cycle["summary"] = self.get_summary(notify_slack=True)
        cycle["finished_at"] = datetime.now().isoformat()
        return cycle
