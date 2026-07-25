import logging
from typing import List, Dict, Any, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, token: str = None, channel: str = None):
        self.token = token or Config.SLACK_BOT_TOKEN
        self.channel = channel or Config.SLACK_CHANNEL
        self.client: Optional[WebClient] = None
        if self.token:
            try:
                self.client = WebClient(token=self.token)
            except Exception as e:
                logger.error(f"Failed to init Slack client: {e}")

    def is_configured(self) -> bool:
        return self.client is not None and self.token != ""

    def _send_message(self, blocks: List[Dict] = None, text: str = "") -> bool:
        if not self.is_configured():
            logger.warning("Slack is not configured; skipping notification.")
            return False
        try:
            kwargs = {"channel": self.channel, "text": text}
            if blocks:
                kwargs["blocks"] = blocks
            self.client.chat_postMessage(**kwargs)
            return True
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            return False
        except Exception as e:
            logger.exception("Unexpected error sending Slack message")
            return False

    # ---------- Notifications ----------

    def notify_failed_emails(self, failed_list: List[Dict[str, Any]]) -> bool:
        if not failed_list:
            return self._send_message(
                text=":white_check_mark: All emails delivered successfully. No failures.",
            )

        header = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: *Email Delivery Failures Report*\n\n"
                            f"*Total failed:* {len(failed_list)} email(s) could not be delivered."
                }
            },
            {"type": "divider"},
        ]

        items = []
        for idx, f in enumerate(failed_list, 1):
            name = f.get("name") or "N/A"
            email = f.get("email", "N/A")
            error = f.get("error", "Unknown error")
            items.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{idx}.* *{name}*\n"
                            f":e-mail: `{email}`\n"
                            f":warning: Error: {error}"
                }
            })

        email_list = ", ".join(f"`{f.get('email')}`" for f in failed_list)
        footer = [
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Failed email IDs:* {email_list}"
                    }
                ]
            }
        ]

        summary = f"FAILED EMAILS ({len(failed_list)}): " + ", ".join(
            f"{f.get('email')}" for f in failed_list
        )
        return self._send_message(blocks=header + items + footer, text=summary)

    def notify_responders(self, replies: List[Dict[str, Any]]) -> bool:
        if not replies:
            return self._send_message(
                text=":inbox_tray: No new email responses detected this cycle."
            )

        header = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":inbox_tray: *New Email Responses Received*\n\n"
                            f"*Total responses:* {len(replies)} new reply/replies."
                }
            },
            {"type": "divider"},
        ]

        items = []
        for idx, r in enumerate(replies, 1):
            from_addr = r.get("from_address", "N/A")
            subj = r.get("subject", "(no subject)")
            at = r.get("replied_at", "N/A")
            ack = r.get("is_acknowledgment")
            tag = ":ok_hand:" if ack else ":speech_balloon:"
            items.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{idx}.* {tag} *From:* `{from_addr}`\n"
                            f"*Subject:* {subj}\n"
                            f"*At:* {at}"
                }
            })

        footer = [
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":bar_chart: *Breakdown:*\n"
                            f"- *Detailed replies:* {sum(1 for r in replies if not r.get('is_acknowledgment'))}\n"
                            f"- *Acknowledgments only:* {sum(1 for r in replies if r.get('is_acknowledgment'))}"
                }
            }
        ]

        summary = f"NEW RESPONSES ({len(replies)}): " + ", ".join(
            r.get("from_address") for r in replies
        )
        return self._send_message(blocks=header + items + footer, text=summary)

    def notify_non_responders(self, non_responders: List[Dict[str, Any]]) -> bool:
        if not non_responders:
            return self._send_message(
                text=":wave: Everyone has responded. No pending non-responders."
            )

        header = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":snooze: *Non-Responder Report*\n\n"
                            f"*Total without reply/acknowledgment:* {len(non_responders)} contact(s)."
                }
            },
            {"type": "divider"},
        ]

        items = []
        for idx, nr in enumerate(non_responders, 1):
            name = nr.get("name") or "N/A"
            email = nr.get("email_address", "N/A")
            company = nr.get("company") or "N/A"
            attempt = nr.get("attempt_number", 1)
            sent_at = nr.get("sent_at", "N/A")
            items.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{idx}.* *{name}* @ {company}\n"
                            f":e-mail: `{email}`\n"
                            f":calendar: Original email at: {sent_at} | "
                            f":repeat: Attempt #{attempt}"
                }
            })

        summary = f"NON-RESPONDERS ({len(non_responders)}): " + ", ".join(
            nr.get("email_address") for nr in non_responders
        )
        return self._send_message(blocks=header + items, text=summary)

    def notify_retargeting(self, retargeted: List[Dict[str, Any]]) -> bool:
        if not retargeted:
            return self._send_message(
                text=":repeat: No contacts eligible for retargeting this cycle."
            )

        header = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":repeat: *Retargeting Campaign Started*\n\n"
                            f"*Retargeting:* {len(retargeted)} contact(s) after "
                            f"{Config.RETARGET_AFTER_DAYS} days of no reply."
                }
            },
            {"type": "divider"},
        ]

        items = []
        for idx, r in enumerate(retargeted, 1):
            name = r.get("name") or "N/A"
            email = r.get("email_address", "N/A")
            items.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{idx}.* *{name}* — `{email}`"
                }
            })

        summary = f"RETARGETED ({len(retargeted)}): " + ", ".join(
            r.get("email_address") for r in retargeted
        )
        return self._send_message(blocks=header + items, text=summary)

    def notify_summary(self, summary: Dict[str, Any]) -> bool:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":bar_chart: *Email Campaign Summary Report*"
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Emails:*\n{summary.get('total', 0)}"},
                    {"type": "mrkdwn", "text": f"*Sent:*\n{summary.get('sent', 0)}"},
                    {"type": "mrkdwn", "text": f"*Failed:*\n{summary.get('failed', 0)}"},
                    {"type": "mrkdwn", "text": f"*Replied:*\n{summary.get('replied', 0)}"},
                    {"type": "mrkdwn", "text": f"*Acknowledged:*\n{summary.get('acknowledged', 0)}"},
                    {"type": "mrkdwn", "text": f"*No Reply:*\n{summary.get('no_reply', 0)}"},
                    {"type": "mrkdwn", "text": f"*Retargeted:*\n{summary.get('retargeted', 0)}"},
                ]
            }
        ]
        return self._send_message(blocks=blocks, text=f"Summary: {summary}")
