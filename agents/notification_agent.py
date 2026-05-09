"""
Stage 6 — Notification Agent

Two notification modes:
  • run_daily()   — Posts daily card summary only
  • run_monthly() — Posts billing + reconciliation summaries with report attachments

Degrades gracefully when SLACK_BOT_TOKEN is empty (smoke-test safe).
"""

import os
from logger import get_logger
from dotenv import load_dotenv

load_dotenv()
log = get_logger(__name__)

SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#billing-alerts")
ATTACH_REPORTS = os.environ.get("ATTACH_REPORTS", "true").lower() == "true"


def _get_client():
    """Return a Slack WebClient or None if no token."""
    if not SLACK_TOKEN:
        log.warning("SLACK_BOT_TOKEN is empty — skipping Slack notifications")
        return None
    from slack_sdk import WebClient
    return WebClient(token=SLACK_TOKEN)


def _post_message(client, channel, text):
    response = client.chat_postMessage(channel=channel, text=text)
    log.debug("Slack message sent to %s (ts: %s)", channel, response["ts"])


def _upload_file(client, channel, filepath, title):
    client.files_upload_v2(
        channel=channel, file=filepath, title=title,
        filename=os.path.basename(filepath),
    )
    log.debug("Uploaded %s to %s", filepath, channel)


def run_daily(billing_summary):
    """Send daily card summary alert when a new file is uploaded."""
    log.info("Daily notification started")

    client = _get_client()
    if not client:
        return

    daily = billing_summary.get("daily", {})
    daily_msg = (
        ":bar_chart: *Daily Card Summary*\n"
        f"• New cards created today: {daily.get('new_today', 0)}\n"
        f"• New cards this week: {daily.get('new_this_week', 0)}\n"
        f"• New cards this month: {daily.get('new_this_month', 0)}\n"
        f"• Total active cards: {billing_summary['total_cards']}\n"
        f"• Cards ≤ 3 months old: {billing_summary['breakdown']['tier_3_dollar']}\n"
        f"• Cards > 3 months old: {billing_summary['breakdown']['tier_1_dollar']}"
    )
    _post_message(client, SLACK_CHANNEL, daily_msg)

    log.info("Daily card summary posted to %s", SLACK_CHANNEL)


def run_monthly(billing_summary, recon_summary, report_paths):
    """Send monthly billing + reconciliation summaries with report attachments."""
    log.info("Monthly notification started")

    client = _get_client()
    if not client:
        return

    # --- Billing summary ---
    billing_msg = (
        ":moneybag: *Billing Summary*\n"
        f"• Total cards: {billing_summary['total_cards']}\n"
        f"• Total revenue: ${billing_summary['total_revenue']:.2f}\n"
        f"• Avg months active: {billing_summary['avg_months']}\n"
        f"• Tier $3: {billing_summary['breakdown']['tier_3_dollar']}\n"
        f"• Tier $1: {billing_summary['breakdown']['tier_1_dollar']}"
    )
    _post_message(client, SLACK_CHANNEL, billing_msg)

    # --- Reconciliation summary ---
    recon_msg = (
        ":mag: *Reconciliation Summary*\n"
        f"• Matched: {recon_summary['matched']}\n"
        f"• Deleted: {len(recon_summary['deleted'])}\n"
        f"• Missing: {len(recon_summary['missing'])}"
    )
    if recon_summary.get("skipped"):
        recon_msg += "\n_Reconciliation was skipped (no credentials)._"
    _post_message(client, SLACK_CHANNEL, recon_msg)

    log.info("Billing + reconciliation summaries posted to %s", SLACK_CHANNEL)

    # --- Attach reports ---
    if ATTACH_REPORTS and report_paths:
        billing_report, recon_report = report_paths
        if os.path.isfile(billing_report):
            _upload_file(client, SLACK_CHANNEL, billing_report, "Billing Report")
        if os.path.isfile(recon_report):
            _upload_file(client, SLACK_CHANNEL, recon_report, "Reconciliation Report")

    log.info("Monthly notification complete")
