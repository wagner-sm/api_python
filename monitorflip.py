import urllib.request
import urllib.parse
import json
import sys
import re

AIRLINES = {
    "LA": "LATAM",
    "G3": "Gol",
    "AD": "Azul",
}


def get_airline(image_url):
    if not image_url:
        return None
    match = re.search(r"/([A-Z0-9]+)\.(png|jpg|webp|svg)", image_url, re.IGNORECASE)
    code = match.group(1).upper() if match else None
    return AIRLINES.get(code, code)


def fetch_flipmilhas(date, origin, destiny):
    params = {
        "adults": "1",
        "babies": "0",
        "back_date": "",
        "children": "0",
        "class": "economica",
        "departure_date": date,
        "destiny": destiny.upper(),
        "origin": origin.upper(),
        "rooms": "1",
    }

    qs = urllib.parse.urlencode(params)
    target_url = f"https://flipmilhas.com/passagens?{qs}"
    jina_url = f"https://r.jina.ai/{target_url}"

    req = urllib.request.Request(
        jina_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "Mozilla/5.0 (compatible; MonitorFlip/1.0)",
            "X-Timeout": "30",
        },
    )

    with urllib.request.urlopen(req, timeout=90) as resp:
        body = resp.read().decode("utf-8")

    # Extract first image URL from markdown image syntax ![...](url)
    image_match = re.search(r"!\[.*?\]\((https?://[^)]+)\)", body)
    first_image_url = image_match.group(1) if image_match else None

    title_match = re.search(
        r"Title:\s*Passagens\s+\w+\s*→\s*\w+\s+a partir de\s*R\$\s*([\d.,]+)",
        body
    )

    if title_match:
        price_str = title_match.group(1).replace(".", "").replace(",", ".")
        return float(price_str), target_url, first_image_url

    alt_match = re.search(r"R\$\s*([\d.,]+)", body)
    if alt_match:
        price_str = alt_match.group(1).replace(".", "").replace(",", ".")
        return float(price_str), target_url, first_image_url

    return None, target_url, first_image_url


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    date = payload.get("date", "").strip()
    origin = payload.get("origin", "").strip()
    destiny = payload.get("destiny", "").strip()

    if not date or not origin or not destiny:
        print(json.dumps({
            "error": "Missing required fields: date, origin, destiny"
        }))
        sys.exit(1)

    price, source_url, first_image_url = fetch_flipmilhas(date, origin, destiny)
    company = get_airline(first_image_url)

    if price is not None:
        price_str = f"{price:.2f}".replace(".", ",")
        print(json.dumps({
            "origin": origin.upper(),
            "destiny": destiny.upper(),
            "date": date,
            "lowest_price": price_str,
            "company": company,
            "source": source_url
        }, ensure_ascii=False))

    else:
        print(json.dumps({
            "origin": origin.upper(),
            "destiny": destiny.upper(),
            "date": date,
            "lowest_price": None,
            "company": company,
            "error": "Price not found",
            "source": source_url
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()