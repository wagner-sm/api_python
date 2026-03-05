import os
import hashlib
import logging
import time
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------------------
# PLAYWRIGHT
# ---------------------------------------------------------------------------

def create_context(playwright):
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=os.environ.get("CHROME_BIN", "/usr/bin/chromium"),
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    # Bloqueia apenas imagens, fontes e mídia — NÃO bloquear CSS pois
    # alguns sites (ex: URBS) dependem de stylesheet para renderizar conteúdo
    context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "font", "media")
        else route.continue_(),
    )
    return browser, context


def fetch_html(page, url: str) -> str:
    try:
        # networkidle aguarda a rede ficar quieta — garante que JS terminou
        page.goto(url, wait_until="networkidle", timeout=45_000)
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector("body", timeout=15_000)
    except PlaywrightTimeout:
        pass

    page.wait_for_timeout(8_000)

    try:
        page.evaluate("window.stop()")
    except Exception:
        pass

    return page.content()


# ---------------------------------------------------------------------------
# EXTRAÇÃO DE CONTEÚDO
# ---------------------------------------------------------------------------

def extract_content(html: str, url: str) -> str:
    if not html:
        return ""

    if "cartaometrocard.com.br" in url:
        return _extract_metrocard(html)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    titles = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(" ", strip=True)
        if len(text) >= 10:
            titles.append(text)

    return "\n".join(sorted(set(titles)))


def _extract_metrocard(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table tbody tr, table tr")

        results = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                tipo = cells[0].get_text(strip=True) or "N/A"
                linha = cells[1].get_text(strip=True) or "N/A"
                link = row.find("a")
                href = link.get("href", "") if link else ""
                results.append(f"{tipo}-{linha}-{href}")

        lines = sorted(set(r.strip() for r in results if r.strip()))
        return "\n".join(lines)

    except Exception as e:
        logging.error(f"Erro ao extrair metrocard: {e}")
        return ""


def calculate_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def site_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    return domain.split(".")[0].upper()


# ---------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ---------------------------------------------------------------------------

def run_monitor(sites: list) -> list:
    """
    Processa cada site e retorna lista com resultado por URL.

    Retorna:
    [
      {"url": "https://...", "name": "SITE", "hash": "abc123", "ok": True,  "error": None},
    ]

    O n8n compara o hash com o salvo no Supabase e decide se houve mudança.
    """
    results = []

    with sync_playwright() as playwright:
        browser, context = create_context(playwright)

        try:
            page = context.new_page()

            for url in sites:
                name = site_name(url)
                logging.info(f"Verificando {name}: {url}")

                try:
                    html = fetch_html(page, url)

                    if len(html) < 5000:
                        raise ValueError(f"HTML muito pequeno ({len(html)} bytes)")

                    content = extract_content(html, url)

                    if not content or len(content) < 50:
                        raise ValueError(f"Conteudo invalido ({len(content)} chars)")

                    results.append({
                        "url":   url,
                        "name":  name,
                        "hash":  calculate_hash(content),
                        "ok":    True,
                        "error": None,
                    })

                    logging.info(f"OK {name} ({len(content)} chars)")
                    time.sleep(2)

                except Exception as e:
                    logging.error(f"Erro em {name}: {e}")
                    results.append({
                        "url":   url,
                        "name":  name,
                        "hash":  None,
                        "ok":    False,
                        "error": str(e),
                    })

        finally:
            context.close()
            browser.close()

    return results
