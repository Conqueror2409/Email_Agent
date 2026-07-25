import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "")

    IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#email-notifications")

    RETARGET_AFTER_DAYS = int(os.getenv("RETARGET_AFTER_DAYS", "3"))
    MAX_RETARGET_ATTEMPTS = int(os.getenv("MAX_RETARGET_ATTEMPTS", "2"))
    REPLY_CHECK_INTERVAL_HOURS = int(os.getenv("REPLY_CHECK_INTERVAL_HOURS", "6"))

    DB_PATH = os.getenv("DB_PATH", "email_agent.db")

    @classmethod
    def validate_email_config(cls):
        errors = []
        if not cls.EMAIL_USERNAME:
            errors.append("EMAIL_USERNAME is not set")
        if not cls.EMAIL_PASSWORD:
            errors.append("EMAIL_PASSWORD is not set")
        return errors

    @classmethod
    def validate_slack_config(cls):
        errors = []
        if not cls.SLACK_BOT_TOKEN:
            errors.append("SLACK_BOT_TOKEN is not set")
        return errors
