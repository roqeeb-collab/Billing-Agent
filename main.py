"""
main.py — Pipeline Orchestrator

Two modes:
  • daily   — Ingest new file, compute card stats, send daily alert to Slack
  • monthly — Full 6-stage pipeline (billing, reconciliation, reporting, notification)

Usage:
  python main.py --mode daily
  python main.py --mode monthly   (default)
"""

import sys
import argparse
import time
from logger import get_logger
from dotenv import load_dotenv

load_dotenv()
log = get_logger("pipeline")


def _slack_alert(message):
    """Best-effort Slack alert for pipeline failures."""
    import os
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_CHANNEL", "#billing-alerts")
    if not token:
        log.warning("Cannot send Slack alert (no token): %s", message)
        return
    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        client.chat_postMessage(channel=channel, text=f":rotating_light: Pipeline Alert: {message}")
    except Exception as exc:
        log.error("Failed to send Slack alert: %s", exc)


def _ingest_with_retry():
    """Run ingestion with up to 3 retries."""
    from agents import ingestion_agent
    for attempt in range(1, 4):
        try:
            log.info("Ingestion (attempt %d/3)", attempt)
            return ingestion_agent.run()
        except Exception as exc:
            log.error("Ingestion attempt %d failed: %s", attempt, exc)
            if attempt == 3:
                msg = f"Ingestion failed after 3 attempts: {exc}"
                _slack_alert(msg)
                log.critical(msg)
                sys.exit(1)
            time.sleep(1)


def run_daily():
    """Daily mode: ingest new file → compute stats → send daily card alert."""
    log.info("=" * 60)
    log.info("DAILY RUN STARTED")
    log.info("=" * 60)
    start = time.time()

    # Ingest
    df = _ingest_with_retry()

    # Validate
    try:
        log.info("Validation")
        from agents import validation_agent
        df = validation_agent.run(df)
    except ValueError:
        log.critical("Pipeline halted — validation threshold breached")
        sys.exit(1)
    except Exception as exc:
        msg = f"Validation failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Compute billing stats (needed for daily card counts)
    try:
        log.info("Computing card stats")
        from agents import billing_agent
        df, billing_summary = billing_agent.run(df)
    except Exception as exc:
        msg = f"Billing stats failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Send daily notification only
    try:
        log.info("Sending daily card alert")
        from agents import notification_agent
        notification_agent.run_daily(billing_summary)
    except Exception as exc:
        msg = f"Daily notification failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    elapsed = time.time() - start
    log.info("=" * 60)
    log.info("DAILY RUN COMPLETED in %.1f seconds", elapsed)
    log.info("=" * 60)


def run_monthly():
    """Monthly mode: full 6-stage pipeline."""
    log.info("=" * 60)
    log.info("MONTHLY RUN STARTED")
    log.info("=" * 60)
    start = time.time()

    # Stage 1: Ingestion
    df = _ingest_with_retry()

    # Stage 2: Validation
    try:
        log.info("Stage 2/6 — Validation")
        from agents import validation_agent
        df = validation_agent.run(df)
    except ValueError:
        log.critical("Pipeline halted — validation threshold breached")
        sys.exit(1)
    except Exception as exc:
        msg = f"Validation failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Stage 3: Billing
    try:
        log.info("Stage 3/6 — Billing")
        from agents import billing_agent
        df, billing_summary = billing_agent.run(df)
    except Exception as exc:
        msg = f"Billing failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Stage 4: Reconciliation
    try:
        log.info("Stage 4/6 — Reconciliation")
        from agents import reconciliation_agent
        recon_summary = reconciliation_agent.run(df)
    except Exception as exc:
        msg = f"Reconciliation failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Stage 5: Reporting
    try:
        log.info("Stage 5/6 — Reporting")
        from agents import reporting_agent
        report_paths = reporting_agent.run(df, billing_summary, recon_summary)
    except Exception as exc:
        msg = f"Reporting failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    # Stage 6: Notification (monthly — billing + recon summaries)
    try:
        log.info("Stage 6/6 — Notification")
        from agents import notification_agent
        notification_agent.run_monthly(billing_summary, recon_summary, report_paths)
    except Exception as exc:
        msg = f"Notification failed: {exc}"
        _slack_alert(msg)
        log.critical(msg)
        sys.exit(1)

    elapsed = time.time() - start
    log.info("=" * 60)
    log.info("MONTHLY RUN COMPLETED in %.1f seconds", elapsed)
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Billing Pipeline")
    parser.add_argument(
        "--mode",
        choices=["daily", "monthly"],
        default="monthly",
        help="Run mode: 'daily' for new-file card alerts, 'monthly' for full pipeline (default: monthly)",
    )
    args = parser.parse_args()

    if args.mode == "daily":
        run_daily()
    else:
        run_monthly()
