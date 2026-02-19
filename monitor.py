"""
Monitor API - Lógica de monitoramento sem Supabase
Hash e conteúdo são gerenciados pelo n8n
"""

import os
import hashlib
import logging
import time
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------------------
# SELENIUM
# ---------------------------------------------------------------------------

def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1280,720")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.page_load_strategy = "none"
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.javascript": 1,
    }
    options.add_experimental_option("prefs", prefs)

    options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    service = Service(os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    return driver


def fetch_html(driver: webdriver.Chrome, url: str) -> str:
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except TimeoutException:
        pass
    time.sleep(8)
    try:
        driver.execute_script("window.stop();")
    except Exception:
        pass
    return driver.page_source


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
    from urllib.parse import urlparse
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
    driver = None
    results = []

    try:
        driver = create_driver()

        for url in sites:
            name = site_name(url)
            logging.info(f"Verificando {name}: {url}")

            try:
                html = fetch_html(driver, url)

                if len(html) < 5000:
                    raise ValueError(f"HTML muito pequeno ({len(html)} bytes)")

                content = extract_content(html, url)

                if not content or len(content) < 50:
                    raise ValueError(f"Conteudo invalido ({len(content)} chars)")

                results.append({
                    "url":     url,
                    "name":    name,
                    "hash":    calculate_hash(content),
                    "ok":      True,
                    "error":   None,
                })

                logging.info(f"OK {name} ({len(content)} chars)")
                time.sleep(2)

            except Exception as e:
                logging.error(f"Erro em {name}: {e}")
                results.append({
                    "url":     url,
                    "name":    name,
                    "hash":    None,
                    "ok":      False,
                    "error":   str(e),
                })

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return results
