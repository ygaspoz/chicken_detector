import os
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

def get_ha_snapshot():
    url =f"{HA_URL}/api/template"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    template_payload = {
        "template": "{{ ((as_datetime(state_attr('sun.sun', 'next_setting')) + timedelta(minutes=30)) | as_local).strftime('%H:%M') }}"
    }

    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    response = session.post(url, headers=headers, json=template_payload, timeout=15)

    if response.status_code == 200:
        target_time = response.text.strip()
        print(f"Target Time: {target_time}")
    else:
        print(f"Error {response.status_code}: {response.text}")
get_ha_snapshot()