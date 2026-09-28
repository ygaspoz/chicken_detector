import base64
import os
import json
import requests
from gradio_client import Client, handle_file
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
import os
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

load_dotenv()

HA_URL = os.getenv("HA_URL")
TOKEN = os.getenv("HA_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Added `as_local` to convert from UTC to your Home Assistant's local timezone
template_payload = {
    "template": "{{ ((as_datetime(state_attr('sun.sun', 'next_setting')) + timedelta(minutes=30)) | as_local).strftime('%H:%M') }}"
}

response = requests.post(
    f"{HA_URL}/api/template",
    headers=headers,
    json=template_payload
)

if response.status_code == 200:
    target_time = response.text.strip()
    print(f"Target Time: {target_time}")
else:
    print(f"Error {response.status_code}: {response.text}")