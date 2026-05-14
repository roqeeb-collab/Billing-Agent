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


def run_daily(billing_summary, report_paths=None):
    """Send daily card summary alert when a new file is uploaded."""
    log.info("Daily notification started")
    
    client = _get_client()
    if not client:
        return

    breakdown_lines = []
    for day in billing_summary.get("daily_breakdown", []):
        breakdown_lines.append(f"  └ {day['date']}: {day['count']} cards (${day['revenue']:,.2f})")
    
    breakdown_str = "\n".join(breakdown_lines)

    daily_msg = (
        ":moneybag: *Daily Billing Summary*\n"
        f"• Total cards: {billing_summary['total_cards']:,}\n"
        "*Daily Breakdown:*\n"
        f"{breakdown_str}\n"
        f"• Total revenue: ${billing_summary['total_revenue']:,.2f}\n"
        f"• Avg months active: {billing_summary['avg_months']:.1f}\n"
        f"• Tier $3: {billing_summary['breakdown']['tier_3_count']:,} (${billing_summary['breakdown']['tier_3_revenue']:,.2f})\n"
        f"• Tier $1: {billing_summary['breakdown']['tier_1_count']:,} (${billing_summary['breakdown']['tier_1_revenue']:,.2f})"
    )
    _post_message(client, SLACK_CHANNEL, daily_msg)

    # Attach reports if provided (e.g., Tier 1 Debit List)
    if ATTACH_REPORTS and report_paths:
        for path in report_paths:
            if os.path.isfile(path):
                _upload_file(client, SLACK_CHANNEL, path, "Daily Report Attachment")

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
        f"• Total cards: {billing_summary['total_cards']:,}\n"
        f"• Total revenue: ${billing_summary['total_revenue']:,.2f}\n"
        f"• Avg months active: {billing_summary['avg_months']:.1f}\n"
        f"• Tier $3: {billing_summary['breakdown']['tier_3_count']:,} (${billing_summary['breakdown']['tier_3_revenue']:,.2f})\n"
        f"• Tier $1: {billing_summary['breakdown']['tier_1_count']:,} (${billing_summary['breakdown']['tier_1_revenue']:,.2f})"
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
