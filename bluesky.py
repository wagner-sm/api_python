import sys
import json
from datetime import datetime, timedelta, timezone
import requests

BLUESKY_API = "https://public.api.bsky.app/xrpc"

def resolve_handle(handle):
    resp = requests.get(
        f"{BLUESKY_API}/com.atproto.identity.resolveHandle",
        params={"handle": handle},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["did"]

def get_feed(did, limit):
    resp = requests.get(
        f"{BLUESKY_API}/app.bsky.feed.getAuthorFeed",
        params={"actor": did, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def extract_images(record, did):
    images = []
    embed = record.get("embed")
    if embed and embed.get("$type") == "app.bsky.embed.images":
        for img in embed.get("images", []):
            cid = img["image"]["ref"]["$link"]
            ext = "jpeg" if "jpeg" in img["image"].get("mimeType", "") else "png"
            url = f"https://cdn.bsky.app/img/feed_fullsize/plain/{did}/{cid}@{ext}"
            images.append({"url": url, "mime_type": f"image/{ext}"})
    return images

def main():
    handle = sys.argv[1] if len(sys.argv) > 1 else "esportesnatv.bsky.social"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    flat = sys.argv[3].lower() != "false" if len(sys.argv) > 3 else True

    did = resolve_handle(handle)
    feed = get_feed(did, limit)

    # Pega o post mais recente que tem imagem
    for item in feed.get("feed", []):
        if "reason" in item:
            continue
        post = item["post"]
        record = post["record"]
        images = extract_images(record, did)
        if not images:
            continue

        if flat:
            items = []
            for img in images:
                items.append({
                    "uri": post["uri"],
                    "caption": record.get("text", ""),
                    "url": img["url"],
                    "mime_type": img["mime_type"],
                })
            print(json.dumps(items, ensure_ascii=False))
        else:
            print(json.dumps({"posts": [{
                "uri": post["uri"],
                "text": record.get("text", ""),
                "createdAt": record.get("createdAt", ""),
                "images": images,
            }]}, ensure_ascii=False))
        return  # para após o primeiro post com imagem

    print(json.dumps([], ensure_ascii=False))

if __name__ == "__main__":
    main()