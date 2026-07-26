import json
import sys
import logging
command="default"

from email_agent import EmailAgent
from scheduler import run_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def cmd_send(args):
    agent = EmailAgent()
    recipients = []
    if args.csv:
        recipients = agent.load_recipients_from_csv(args.csv)
    elif args.json:
        recipients = agent.load_recipients_from_json(args.json)
    else:
        print("Please provide --csv or --json file with recipients")
        sys.exit(1)
    print(f"Loaded {len(recipients)} recipient(s)")
    result = agent.send_campaign(recipients, notify_slack=not args.no_slack)
    print(json.dumps(result, indent=2, default=str))


def cmd_check_replies(args):
    agent = EmailAgent()
    result = agent.check_replies(since_days=args.since_days,
                                 notify_slack=not args.no_slack)
    print(json.dumps(result, indent=2, default=str))


def cmd_report_non_responders(args):
    agent = EmailAgent()
    result = agent.report_non_responders(notify_slack=not args.no_slack)
    print(json.dumps(result, indent=2, default=str))


def cmd_retarget(args):
    agent = EmailAgent()
    result = agent.run_retargeting(notify_slack=not args.no_slack)
    print(json.dumps(result, indent=2, default=str))


def cmd_summary(args):
    agent = EmailAgent()
    result = agent.get_summary(notify_slack=not args.no_slack)
    lightweight = {
        "summary": {k: v for k, v in result.items()
                    if k in ("sent", "failed", "replied", "acknowledged",
                             "no_reply", "retargeted", "total")},
        "replies_count": len(result.get("replies", [])),
        "non_responders_count": len(result.get("non_responders", [])),
        "failed_list": result.get("failed", []),
    }
    print(json.dumps(lightweight, indent=2, default=str))


def cmd_cycle(args):
    agent = EmailAgent()
    kwargs = {"send_new": False}
    if args.csv or args.json:
        recipients = []
        if args.csv:
            recipients = agent.load_recipients_from_csv(args.csv)
        else:
            recipients = agent.load_recipients_from_json(args.json)
        kwargs["recipients"] = recipients
        kwargs["send_new"] = True
        print(f"Loaded {len(recipients)} recipient(s) for new campaign")
    result = agent.run_full_cycle(**kwargs)
    print(json.dumps(result, indent=2, default=str))


def cmd_scheduler(args):
    run_scheduler(initial_cycle=not args.no_initial)


def main():
    parser = argparse.ArgumentParser(
        prog="email-agent",
        description="Email Automation Agent: send personalized emails, track replies, notify on Slack, retarget non-responders.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_send = sub.add_parser("send", help="Send a personalized email campaign")
    p_send.add_argument("--csv", help="Path to recipients CSV file")
    p_send.add_argument("--json", help="Path to recipients JSON file")
    p_send.add_argument("--no-slack", action="store_true", help="Skip Slack notifications")
    p_send.set_defaults(func=cmd_send)

    p_check = sub.add_parser("check-replies", help="Check inbox for replies/acknowledgments")
    p_check.add_argument("--since-days", type=int, default=14)
    p_check.add_argument("--no-slack", action="store_true")
    p_check.set_defaults(func=cmd_check_replies)

    p_nr = sub.add_parser("non-responders", help="List who hasn't replied/acknowledged")
    p_nr.add_argument("--no-slack", action="store_true")
    p_nr.set_defaults(func=cmd_report_non_responders)

    p_rt = sub.add_parser("retarget", help="Retarget non-responders (after RETARGET_AFTER_DAYS)")
    p_rt.add_argument("--no-slack", action="store_true")
    p_rt.set_defaults(func=cmd_retarget)

    p_sum = sub.add_parser("summary", help="Print campaign summary")
    p_sum.add_argument("--no-slack", action="store_true")
    p_sum.set_defaults(func=cmd_summary)

    p_cycle = sub.add_parser("cycle", help="Run the full cycle: reply-check, non-responder report, retarget (and optionally send new campaign)")
    p_cycle.add_argument("--csv", help="Optional: CSV file of new recipients")
    p_cycle.add_argument("--json", help="Optional: JSON file of new recipients")
    p_cycle.set_defaults(func=cmd_cycle)

    p_sched = sub.add_parser("scheduler", help="Start the continuous scheduler (runs cycle every N hours)")
    p_sched.add_argument("--no-initial", action="store_true",
                         help="Do not run a cycle immediately on startup")
    p_sched.set_defaults(func=cmd_scheduler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
