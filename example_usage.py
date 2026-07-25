"""
Quick-start example: use EmailAgent as a library in Python.

Before running:
1. cp .env.example .env
2. Edit .env with your SMTP/IMAP credentials and Slack token.
3. pip install -r requirements.txt
"""

from pprint import pprint
from email_agent import EmailAgent


def main():
    agent = EmailAgent(sender_name="Your Name", our_company="Your Company")

    errors = agent.validate()
    if errors:
        print("WARNING:", errors)

    recipients = [
        {
            "to_email": "alice@example.com",
            "to_name": "Alice Johnson",
            "company": "Acme Corp",
            "context_tag": "sales_intro",
            "extra_vars": {
                "pain_point": "streamlining their customer onboarding",
            },
        },
        {
            "to_email": "bob@example.com",
            "to_name": "Bob Smith",
            "company": "Globex Inc.",
            "context_tag": "partnership_proposal",
        },
    ]

    # 1) Send campaign — uncomment only after setting real credentials
    # result = agent.send_campaign(recipients, notify_slack=True)
    # pprint(result)

    # 2) Check inbox for new replies
    replies = agent.check_replies(since_days=14, notify_slack=True)
    pprint(replies)

    # 3) Report non-responders to Slack
    non_responders = agent.report_non_responders(notify_slack=True)
    pprint(non_responders)

    # 4) Retarget people who haven't replied in 3+ days
    retarget = agent.run_retargeting(notify_slack=True)
    pprint(retarget)

    # 5) Full summary
    summary = agent.get_summary(notify_slack=True)
    print("\n=== SUMMARY ===")
    pprint({k: v for k, v in summary.items()
            if k in ("sent", "failed", "replied", "acknowledged",
                     "no_reply", "retargeted", "total")})


if __name__ == "__main__":
    main()
