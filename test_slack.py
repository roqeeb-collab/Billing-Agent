import os
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

response = client.chat_postMessage(
    channel=os.getenv("SLACK_CHANNEL"),
    text="✅ Billing Agent Connected Successfully"
)

print(response["ok"])
