import base64
import json
import os
import requests
from dotenv import load_dotenv
from gradio_client import Client, handle_file
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# CONFIGURATION
# ==========================================
load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
LOCAL_IMAGE_PATH = "snapshot.jpg"
TASK_TYPE = "Detection"
CATEGORIES = "chicken"
ha_url = os.getenv("HA_URL")
entity_id = os.getenv("HA_CAMERA_ENTITY_ID")
token = os.getenv("HA_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
ALBUM_ID = os.getenv("IMGBB_ALBUM_ID")

# Google Chat Config
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL")


# ==========================================
# HOME ASSISTANT SNAPSHOT
# ==========================================
def get_ha_snapshot(ha_url, entity_id, token):
    print("Fetching camera snapshot...")
    url = f"{ha_url.rstrip('/')}/api/camera_proxy/{entity_id}"
    headers = {"Authorization": f"Bearer {token}"}

    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False,
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

    script_dir = os.path.dirname(os.path.realpath(__file__))
    abs_image_path = os.path.join(script_dir, image_path) if not os.path.isabs(image_path) else image_path

    if not os.path.exists(abs_image_path):
        raise FileNotFoundError(f"Source image not found: {abs_image_path}")

    try:
        client = Client("nvidia/LocateAnything", token=HF_TOKEN)
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
            api_name="/run_inference",
        )
    except Exception as e:
        raise RuntimeError(f"Hugging Face API request failed: {e}") from e

    if not result or not isinstance(result, (list, tuple)) or len(result) < 3:
        raise RuntimeError(f"Hugging Face returned an unexpected response format: {result}")

    annotated_image_path, raw_text, data = result[0], result[1], result[2]

    if not annotated_image_path or not os.path.exists(annotated_image_path):
        raise RuntimeError(
            f"Hugging Face inference completed, but no output image was generated (path: {annotated_image_path}).\n"
            f"Raw text response: {raw_text}\n"
            f"Data response: {data}"
        )

    if os.path.getsize(annotated_image_path) == 0:
        raise RuntimeError(
            f"Hugging Face returned an empty (0-byte) image file at {annotated_image_path}.\n"
            f"Data response: {data}"
        )

    detections = data.get("detections", []) if isinstance(data, dict) else []
    print(f"Inference complete. Found {len(detections)} object(s).")

    return annotated_image_path, detections


# ==========================================
# 2. Freeimage UPLOAD
# ==========================================

def upload_to_freeimage(file_path: str) -> tuple[str, str]:
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"File to upload does not exist: {file_path}")

    file_size = os.path.getsize(file_path)
    print(f"Uploading output image ({file_size} bytes) to FreeImage.host...")

    url = "https://freeimage.host/api/1/upload"
    payload = {
        "key": "6d207e02198a847aa98d0a2a901485a5",  # Public API key provided by FreeImage
        "action": "upload",
        "format": "json"
    }

    with open(file_path, "rb") as f:
        files = {"source": f}
        res = requests.post(url, data=payload, files=files, timeout=30)

    if res.status_code == 200:
        data = res.json()["image"]
        direct_image_url = data["url"]         # Direct raw .jpg/.png for Google Chat
        viewer_url = data["url_viewer"]        # Web view page for the button
        print(f"Uploaded successfully! Direct URL: {direct_image_url}")
        return direct_image_url, viewer_url
    else:
        raise RuntimeError(f"FreeImage upload failed ({res.status_code}): {res.text}")


# ==========================================
# 3. GOOGLE CHAT CARD V2 MESSAGE
# ==========================================
def send_google_chat_card(webhook_url: str, image_url: str, viewer_link: str, detections: list):
    print("💬 Posting card message to Google Chat...")

    total_count = len(detections)
    target_label = detections[0]["label"] if detections else CATEGORIES

    card_payload = {
        "cardsV2": [
            {
                "cardId": "locateAnythingCard",
                "card": {
                    "header": {
                        "title": "NVIDIA LocateAnything Result",
                        "subtitle": f"Target: {target_label}",
                        "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/center_focus_weak/default/48px.svg",
                        "imageType": "CIRCLE",
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
                                        "altText": "Annotated Detection Output",
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Open in FreeImage",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": viewer_link
                                                    }
                                                },
                                            }
                                        ]
                                    }
                                },
                            ]
                        }
                    ],
                },
            }
        ]
    }

    response = requests.post(
        webhook_url,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps(card_payload),
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
    direct_url, viewer_url = upload_to_freeimage(annotated_path)
    send_google_chat_card(GOOGLE_CHAT_WEBHOOK_URL, direct_url, viewer_url, detections)