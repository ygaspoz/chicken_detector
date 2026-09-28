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
# ==========================================
# CONFIGURATION
# ==========================================
# 1. Hugging Face Config

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
LOCAL_IMAGE_PATH = "snapshot.jpg"
TASK_TYPE = "Detection"
CATEGORIES = "chicken"
ha_url = os.getenv("HA_URL")
entity_id = os.getenv("HA_ENTITY_ID")
token = os.getenv("HA_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
ALBUM_ID=os.getenv("IMGBB_ALBUM_ID")  # Optional: Imgbb Album ID for organizing uploads

# 3. Google Chat Config
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL")  # Incoming Webhook URL for Google Chat

print("Fetching camera snapshot...")
def get_ha_snapshot(ha_url, entity_id, token):
    url = f"{ha_url.rstrip('/')}/api/camera_proxy/{entity_id}"
    headers = {"Authorization": f"Bearer {token}"}

    # Configure retries for SSL/connection drops
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,  # Waits 1s, 2s, 4s between retries
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    response = session.get(url, headers=headers, timeout=15)

    if response.status_code == 200:
        with open(LOCAL_IMAGE_PATH, "wb") as file:
            file.write(response.content)
        print("Snapshot saved successfully!")
    else:
        raise RuntimeError(f"Failed to fetch image: {response.status_code} - {response.text}")
# ==========================================
# 1. HUGGING FACE INFERENCE
# ==========================================
def run_hf_inference(image_path: str, categories: str):
    print("Sending request to Hugging Face (nvidia/LocateAnything)...")
    client = Client("nvidia/LocateAnything", HF_TOKEN)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    abs_image_path = os.path.join(script_dir, image_path) if not os.path.isabs(image_path) else image_path

    if not os.path.exists(abs_image_path):
        raise FileNotFoundError(f"Source image not found: {abs_image_path}")

    # Call endpoint with parameters matching client.view_api()
    result = client.predict(
        input_type="Image",
        image_file=handle_file(abs_image_path),
        video_file=None,
        task_type=TASK_TYPE,
        category=categories,
        model_mode="hybrid",
        temp=0.7,
        top_p=0.9,
        top_k=20,
        short_size=None,
        question_override=None,
        max_video_frames=4,
        api_name="/run_inference"
    )

    annotated_image_path, _, data = result
    detections = data.get("detections", [])
    print(f"Inference complete. Found {len(detections)} object(s).")

    return annotated_image_path, detections


# ==========================================
# 2. IMGBB UPLOAD
# ==========================================
def upload_to_imgbb_album(file_path: str) -> str:
    print("Uploading output image to ImgBB album...")

    with open(file_path, "rb") as file:
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": base64.b64encode(file.read()),
            "album": ALBUM_ID  # <--- Attaches the image directly to your unlisted album
        }
        res = requests.post(url, data=payload)

    if res.status_code == 200:
        data = res.json()["data"]
        # Direct image link for Google Chat card rendering
        direct_image_url = data["url"]
        print(f"Uploaded to album: {direct_image_url}")
        return direct_image_url
    else:
        raise RuntimeError(f"ImgBB upload failed: {res.text}")


# ==========================================
# 3. GOOGLE CHAT CARD V2 MESSAGE
# ==========================================
def send_google_chat_card(webhook_url: str, image_url: str, drive_link: str, detections: list):
    print("💬 Posting card message to Google Chat...")

    total_count = len(detections)
    target_label = detections[0]["label"] if detections else "object"

    card_payload = {
        "cardsV2": [
            {
                "cardId": "locateAnythingCard",
                "card": {
                    "header": {
                        "title": "NVIDIA LocateAnything Result",
                        "subtitle": f"Target: {target_label}",
                        "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/center_focus_weak/default/48px.svg",
                        "imageType": "CIRCLE"
                    },
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": f"<b>Total Detected:</b> {total_count} {target_label}(s)"
                                    }
                                },
                                {
                                    "image": {
                                        "imageUrl": image_url,
                                        "altText": "Annotated Detection Output"
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Open in IMGBB",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": drive_link
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }

    response = requests.post(
        webhook_url,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps(card_payload)
    )

    if response.status_code == 200:
        print("Card successfully posted to Google Chat!")
    else:
        print(f"Failed to post message: {response.status_code}, {response.text}")


# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    get_ha_snapshot(ha_url, entity_id, token)
    annotated_path, detections = run_hf_inference(LOCAL_IMAGE_PATH, CATEGORIES)
    direct_img_url = upload_to_imgbb_album(annotated_path)
    send_google_chat_card(GOOGLE_CHAT_WEBHOOK_URL, direct_img_url, direct_img_url, detections)