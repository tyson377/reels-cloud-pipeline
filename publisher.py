import os
import sys
import json
import argparse
from datetime import datetime, timezone
import requests

CHANNEL_ID = "6af9587bece6dfde5fce6fbd"
MANIFEST_FILE = "schedule_manifest.json"

def get_slot_from_time():
    hour = datetime.now(timezone.utc).hour
    # 03:00 UTC is ~08:30 IST -> Slot 1
    # 11:00 UTC is ~04:30 IST -> Slot 2
    # 14:00-15:00 UTC is ~08:00 IST -> Slot 3
    if 2 <= hour <= 6:
        return "Inside Out"
    elif 9 <= hour <= 13:
        return "Stick Story"
    else:
        return "Tall Tale 3D"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", default="auto", choices=["auto", "morning", "afternoon", "evening", "Inside Out", "Stick Story", "Tall Tale 3D"])
    args = parser.parse_args()

    api_key = os.environ.get("BUFFER_API_KEY")
    if not api_key:
        print("[ERROR] BUFFER_API_KEY environment variable not set!")
        sys.exit(1)

    if not os.path.exists(MANIFEST_FILE):
        print(f"[ERROR] {MANIFEST_FILE} not found!")
        sys.exit(1)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_style = args.slot
    if target_style == "auto":
        target_style = get_slot_from_time()
    elif target_style == "morning":
        target_style = "Inside Out"
    elif target_style == "afternoon":
        target_style = "Stick Story"
    elif target_style == "evening":
        target_style = "Tall Tale 3D"

    print(f"[*] Cloud Publisher Triggered. Target Style/Slot: {target_style}")

    # Find next unposted video for this style
    target_item = None
    target_key = None

    for k, item in manifest.items():
        if not item.get("published") and item.get("style") == target_style:
            target_item = item
            target_key = k
            break

    # If no video found for that exact style, pick any next unposted video
    if not target_item:
        print(f"[!] No remaining unposted video for '{target_style}'. Finding next available video...")
        for k, item in manifest.items():
            if not item.get("published"):
                target_item = item
                target_key = k
                break

    if not target_item:
        print("[*] All 150 videos have been published! 🎉")
        return

    print(f"[+] Publishing: '{target_item['title']}' ({target_item.get('style')})")
    video_url = target_item["video_url"]
    caption = target_item["caption"]
    cover_url = target_item.get("cover_url")

    video_asset = {"url": video_url}
    if cover_url:
        video_asset["thumbnailUrl"] = cover_url
        print(f"[+] Attaching Custom Cover Image: {cover_url}")


    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post {
            id
            status
          }
        }
        ... on InvalidInputError {
          message
        }
        ... on LimitReachedError {
          message
        }
        ... on UnexpectedError {
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "channelId": CHANNEL_ID,
            "mode": "shareNow",
            "schedulingType": "automatic",
            "needsApproval": False,
            "text": caption,
            "assets": [
                {
                    "video": video_asset
                }
            ],
            "metadata": {
                "instagram": {
                    "type": "reel",
                    "shouldShareToFeed": True
                }
            }
        }
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post("https://api.buffer.com", json={"query": mutation, "variables": variables}, headers=headers, timeout=60).json()

    post = resp.get("data", {}).get("createPost", {}).get("post")
    if not post:
        raise RuntimeError(f"Buffer API error: {resp}")

    post_id = post["id"]
    print(f"[+] SUCCESS! Published to Instagram Reels: Post ID {post_id}")

    target_item["published"] = True
    target_item["published_at"] = datetime.now(timezone.utc).isoformat()
    target_item["buffer_post_id"] = post_id

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("[+] Updated manifest saved.")

if __name__ == "__main__":
    main()
