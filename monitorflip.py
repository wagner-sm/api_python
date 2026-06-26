import urllib.request
import urllib.parse
import json
import sys
import re
from datetime import datetime

AIRLINES = {
    "LA": "LATAM",
    "G3": "Gol",
    "AD": "Azul",
}

MONTHS_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr",
    5: "mai", 6: "jun", 7: "jul", 8: "ago",
    9: "set", 10: "out", 11: "nov", 12: "dez",
}


def get_airline(image_url):
    if not image_url:
        return None
    # Garante que a URL é de companhia aérea conhecida (airlines/static/images/XX.png)
    match = re.search(r"/airlines/static/images/([A-Z0-9]+)\.(png|jpg|webp|svg)", image_url, re.IGNORECASE)
    code = match.group(1).upper() if match else None
    return AIRLINES.get(code, code)


def date_to_display(date_str):
    """Converte '2026-12-12' para '12/12/2026' (formato usado no body do Jina)."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%-d/%m/%Y")  # ex: "12/12/2026"
    except ValueError:
        return None


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
            "X-Timeout": "60",
            # Aguarda o elemento de preço carregar antes de retornar o HTML
            "X-Wait-For-Selector": "[class*='price'],[class*='preco'],[class*='valor']",
        },
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")

    # Companhia: busca especificamente em /airlines/static/images/XX.png
    image_match = re.search(r"https?://[^)]+/airlines/static/images/[A-Z0-9]+\.[a-z]+", body, re.IGNORECASE)
    first_image_url = image_match.group(0) if image_match else None

    # Tenta encontrar preços associados à data no corpo (caso JS tenha carregado)
    date_display = date_to_display(date)  # ex: "12/12/2026"
    price = None

    if date_display:
        # Busca bloco: "Embarque 12/12/2026 ... R$ 294,18"
        match = re.search(
            rf"Embarque\s+{re.escape(date_display)}.{{0,500}}?R\$\s*([\d.,]+)",
            body,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            price_str = match.group(1).replace(".", "").replace(",", ".")
            try:
                price = float(price_str)
            except ValueError:
                pass

    # Fallback: título da página — mas só se o título mencionar a rota correta
    if price is None:
        title_match = re.search(
            r"Title:\s*Passagens\s+(\w+)\s*→\s*(\w+)\s+a partir de\s*R\$\s*([\d.,]+)",
            body,
        )
        if title_match:
            title_origin = title_match.group(1).upper()
            title_destiny = title_match.group(2).upper()
            if title_origin == origin.upper() and title_destiny == destiny.upper():
                price_str = title_match.group(3).replace(".", "").replace(",", ".")
                try:
                    price = float(price_str)
                except ValueError:
                    pass

    return price, target_url, first_image_url


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
        print(json.dumps({
            "origin": origin.upper(),
            "destiny": destiny.upper(),
            "date": date,
            "lowest_price": price,
            "company": company,
            "source": source_url,
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "origin": origin.upper(),
            "destiny": destiny.upper(),
            "date": date,
            "lowest_price": None,
            "company": company,
            "error": "Price not found",
            "source": source_url,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
