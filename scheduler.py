import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config
from email_agent import EmailAgent

logger = logging.getLogger(__name__)


def _cycle_job(agent: EmailAgent):
    try:
        logger.info("Running scheduled email cycle (reply check + non-responder report + retargeting)")
        result = agent.run_full_cycle(send_new=False)
        logger.info(
            "Cycle complete. New replies: %s, Retargeted: %s",
            result.get("replies", {}).get("new_replies_count"),
            result.get("retargeting", {}).get("total_sent"),
        )
    except Exception:
        logger.exception("Scheduled cycle failed")


def run_scheduler(initial_cycle: bool = True):
    agent = EmailAgent()
    errors = agent.validate()
    if errors:
        logger.error("Agent validation failed: %s", "; ".join(errors))
        return

    if initial_cycle:
        logger.info("Running initial cycle at startup")
        _cycle_job(agent)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    hours = max(1, Config.REPLY_CHECK_INTERVAL_HOURS)
    scheduler.add_job(
        _cycle_job,
        trigger=IntervalTrigger(hours=hours),
        args=[agent],
        id="email_cycle",
        name="Email Reply Check + Retarget Cycle",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduler started. Running cycle every %s hour(s). Press Ctrl+C to stop.", hours)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
