# Billing Agent Pipeline

## Overview
The Billing Agent Pipeline is an automated, multi-stage Python orchestrator designed to handle daily and monthly billing workflows. It ingests data, validates records, computes billing statistics, reconciles accounts, generates reports, and sends automated notifications (e.g., via Slack).

## Features
- **Daily Mode**: Ingests new files, computes daily card statistics, and sends a daily alert to Slack.
- **Monthly Mode**: Executes a complete 6-stage pipeline:
  1. **Ingestion**: Fetches and loads data with automatic retries.
  2. **Validation**: Ensures data integrity; halts the pipeline if validation thresholds are breached.
  3. **Billing**: Computes detailed billing summaries and statistics.
  4. **Reconciliation**: Cross-checks and reconciles billing accounts.
  5. **Reporting**: Generates standardized output reports (e.g., Excel files).
  6. **Notification**: Dispatches comprehensive monthly summaries and alerts via Slack.

## Prerequisites
- Python 3.12+
- A `.env` file containing necessary environment variables (e.g., Slack tokens, credentials).

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/roqeeb-collab/Billing-Agent.git
   cd Billing-Agent
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   
   # On Windows use:
   .venv\Scripts\activate
   
   # On macOS/Linux use:
   source .venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration
Before running the pipeline, several configurations must be set up. Create a `.env` file in the root directory of the project with the following required variables:

### 1. Slack Integration (Required)
Used by the `notification_agent` to send alerts and reports.
```env
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL=#billing-alerts
ATTACH_REPORTS=true
```

### 2. Google Sheets Configuration (For Reconciliation)
The `reconciliation_agent` requires access to a Google Sheet via the Google Sheets API. You must provide a service account JSON file.
```env
GOOGLE_SHEET_ID=your-google-sheet-id
GOOGLE_SHEET_TAB_NAME=Sheet1
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
```
**Google Credentials Setup:**
- Go to the [Google Cloud Console](https://console.cloud.google.com/).
- Enable the **Google Sheets API** and **Google Drive API**.
- Create a **Service Account** and generate a JSON key.
- Save the JSON key in the root directory as `credentials.json` (or update `GOOGLE_SERVICE_ACCOUNT_FILE` with its path).
- *Important:* Share your target Google Sheet with the email address of the generated Service Account.

### 3. Data Folders
These specify where the pipeline should look for incoming files and where it should save generated reports.
```env
INPUT_FOLDER=data/input
OUTPUT_FOLDER=data/output
```

*(Note: Make sure your `.env` and `credentials.json` files are never committed to version control. They are already included in the `.gitignore`.)*

## Usage
Run the pipeline orchestrator using the `main.py` script. You can specify the operational mode using the `--mode` argument.

### Daily Run
Executes the daily flow (ingestion, validation, basic billing stats computation, and daily Slack alert):
```bash
python main.py --mode daily
```

### Monthly Run (Default)
Executes the full, exhaustive 6-stage end-to-end pipeline:
```bash
python main.py --mode monthly
```
*(You can also simply run `python main.py` as `monthly` is the default mode)*

## Architecture
The pipeline is designed with modularity in mind, utilizing dedicated "agents" for each specific task located in the `agents/` directory:
- `ingestion_agent.py` - Handles data loading and extraction.
- `validation_agent.py` - Ensures data quality and structural integrity.
- `billing_agent.py` - Performs core billing calculations.
- `reconciliation_agent.py` - Identifies discrepancies and reconciles records.
- `reporting_agent.py` - Formats data into exportable final reports.
- `notification_agent.py` - Manages dispatching of alerts and summaries to external platforms.

This modular structure ensures separation of concerns, making the pipeline robust and easily extensible.
