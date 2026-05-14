# Billing Agent Pipeline

## Overview
The Billing Agent Pipeline is an automated, multi-stage Python orchestrator designed to handle daily and monthly billing workflows. It connects your live data from **Google Sheets** and **Google Drive** to **Slack**, providing real-time billing updates and automated reconciliation.

---

## 🚀 Key Features

### 1. Smart Billing Rules
- **Tiered Pricing**: Automatically calculates fees based on card age.
    - **Tier $3.00**: Cards active for 3 months or less.
    - **Tier $1.00**: Cards active for more than 3 months.
- **Automated Debit Lists**: Generates an Excel report specifically for the $1.00 Tier cards during daily runs, facilitating easy monthly debits.

### 2. Live Data Integration
- **Delta Ingestion**: Daily runs automatically identify and process only **newly added records** from your Google Drive folder.
- **Duplicate Prevention**: Cross-checks every new card against your Master Sheet to ensure no duplicate entries.
- **Google Sheets Reconciliation**: Supports monthly cross-checks between your live data and an end-of-month reference Google Sheet or Excel file.

### 3. Fully Automated Workflows (GitHub Actions)
- **Daily Summary**: Runs every **30 minutes** to check for new files. If new data is found, it sends a summary to Slack with a daily breakdown of cards and revenue.
- **Monthly Audit**: Runs at **1:00 AM on the 1st of every month** to perform a full reconciliation and generate portfolio-wide reports.

---

## 🛠 Operation Modes

### 📅 Daily Mode (`--mode daily`)
Focuses on processing incoming files and keeping you updated on the latest activity.
- **Ingestion**: Scans Drive for the latest upload.
- **Delta Processing**: Returns only the records that aren't already in your Master Sheet.
- **Daily Breakdown**: Slack message includes a chronological breakdown of cards created and revenue generated.
- **Tier 1 Reporting**: Attaches a `tier_1_debit_list.xlsx` if any mature cards ($1 tier) are detected.

### 📊 Monthly Mode (`--mode monthly`)
The full 6-stage audit and reconciliation pipeline.
1. **Full Ingestion**: Loads the entire Master Sheet portfolio.
2. **Validation**: Checks all 1,400+ records for integrity.
3. **Billing**: Computes full revenue stats for the entire history.
4. **Reconciliation**: Compares the Live Master Sheet against a reference Google Sheet/Excel on Drive.
5. **Reporting**: Generates full Billing and Reconciliation Excel reports.
6. **Notification**: Posts the full audit summary and reports to Slack.

---

## ⚙️ Installation & Setup

### 1. Requirements
- Python 3.12+
- Google Cloud Service Account with access to Sheets and Drive.
- Slack Bot with `chat:write` and `files:write` permissions.

### 2. Configuration
Create a `.env` file with the following:
```env
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_CHANNEL=C0B2WNRNLDP
GOOGLE_SHEET_ID=12ieqW7Pg8TUEnc1XaAadS_WPH_6KCRdIm52E8FwQ9lk
GOOGLE_DRIVE_DAILY_FOLDER_ID=13bseNGXVAy9A7j8ky4ecdHdQXKahc_AO
GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID=1dJr5YlARLZqzEa0jwePEjlkGQsLKieM-
```

## 🚀 Deployment to GitHub Actions

To set up the automation so it runs in the cloud (24/7), follow these steps:

### 1. Push Code to GitHub
Ensure all your changes are pushed to your repository:
```bash
git add .
git commit -m "Update automation and billing logic"
git push origin main
```

### 2. Configure GitHub Secrets
The pipeline requires your credentials to be stored securely in GitHub.
1. Navigate to your repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Add the following **Repository Secrets**:
    - **`GOOGLE_CREDENTIALS`**: Paste the entire content of your `credentials.json` file.
    - **`SLACK_BOT_TOKEN`**: Paste your Slack Bot Token (`xoxb-...`).

### 3. Verify Automation
Once the secrets are added:
1. Go to the **Actions** tab on GitHub.
2. Select **"Daily Billing Summary"** and click **"Run workflow"** to test the daily check.
3. Select **"Monthly Billing & Reconciliation"** and click **"Run workflow"** to test the full audit.

---

## 📁 Project Structure
- `agents/` - Modular agents for Ingestion, Billing, Reconciliation, etc.
- `.github/workflows/` - Automation schedules (Daily check and Monthly audit).
- `data/` - Temporary local storage for processing (Ignored by Git).
- `main.py` - Core orchestrator for all modes.
