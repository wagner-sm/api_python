import os
import re
import hashlib
import logging
import time
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import requests
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


# Sites que devem usar SOMENTE Jina Reader (Playwright não funciona)
JINA_ONLY_SITES = [
    # Adicione aqui URLs que o Playwright não consegue acessar
    # "https://exemplo.com/pagina",
]

# Palavras-chave na URL que forçam o uso do Jina Reader
JINA_KEYWORDS = ["alboom"]

# Sites que precisam de extração seletiva (só extrai o que importa, ignora ruído)
SELECTIVE_EXTRACT = [
    r"alboom",
]


def extract_meaningful(jina_markdown: str, url: str) -> str:
    """Extrai apenas os títulos do portfólio do markdown do Jina.

    Remove imagens, blob URLs, query params, contadores de views
    e outros ruídos que causam falsos positivos em sites como Alboom.
    Retorna string com títulos ordenados separados por | para hashear.
    """
    if not jina_markdown:
        return ""

    # --- Fase 1: extrair do markdown original (antes de destruir os links) ---
    nav_links = []
    social = []
    headings_raw = []

    for line in jina_markdown.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Links de redes sociais — extrai só o nome da plataforma
        social_match = re.findall(
            r'\[.*?\]\((https?://(?:www\.)?(facebook|instagram|twitter|pinterest|youtube|linkedin|tiktok)\.com[^)]*)\)',
            line, flags=re.IGNORECASE,
        )
        for _, platform in social_match:
            social.append(platform.lower())

        # Links com texto visível curto = navegação/categorias
        for text in re.findall(r'\[([A-Za-z0-9][^\]]{1,40})\]\([^)]+\)', line):
            text = text.strip()
            if text and not re.search(r'http|\.jpg|\.png|\.gif|\.webp|image\s*\d', text, re.IGNORECASE):
                nav_links.append(text)

        # Títulos (###) — primeiro limpa a linha, depois divide por ###
        if '###' in line:
            clean = line
            # Remove todas as imagens e links
            clean = re.sub(r'!\[.*?\]\(.*?\)', '', clean)
            clean = re.sub(r'\[([^\]]*?)\]\([^)]*\)', r'\1', clean)
            # Remove URL nuas e artefatos
            clean = re.sub(r'http\S+', '', clean)
            clean = re.sub(r'\]\([^)]*\)', '', clean)
            # Divide por ### e processa cada parte (pula a primeira, é anterior ao primeiro ###)
            for part in re.split(r'#{1,3}\s+', clean)[1:]:
                # Limpa boilerplate e números
                part = re.sub(r'veja\s*mais', '', part, flags=re.IGNORECASE)
                part = re.sub(r'\b\d{2,}\b', '', part)
                part = re.sub(r'\s+', ' ', part).strip()
                if len(part) >= 5:
                    headings_raw.append(part)

    # --- Fase 2: limpar tudo para extrair só texto estrutural ---
    md = jina_markdown

    # Remove imagens e links que contêm imagens
    md = re.sub(r'\[!\[.*?\]\(.*?\)\]\(.*?\)', '', md)
    md = re.sub(r'!\[.*?\]\(.*?\)', '', md)

    # Converte links markdown em texto puro: [texto](url) -> texto
    md = re.sub(r'\[([^\]]*?)\]\([^)]*\)', r'\1', md)

    # Remove query params de URLs nuas restantes
    md = re.sub(r'\?[^\s)\]"><]+', '', md)

    # Remove blob URLs
    md = re.sub(r'blob:https?://[^\s)\]"><]+', '', md)

    # Remove "Veja mais"
    md = re.sub(r'veja\s*mais', '', md, flags=re.IGNORECASE)

    # Remove números isolados (contadores de views/fotos)
    md = re.sub(r'\b\d{2,}\b', '', md)

    # Remove caracteres de lista e asteriscos de negrito
    md = re.sub(r'[*]{1,2}', '', md)

    # Extrai títulos (###) do texto limpo
    headings = []
    for line in md.split('\n'):
        line = line.strip()
        if not line:
            continue
        h_match = re.search(r'#{1,3}\s+(.+)', line)
        if h_match:
            text = h_match.group(1).strip()
            if len(text) >= 5:
                headings.append(text)

    # --- Fase 3: juntar, filtrar boilerplate e deduplicar ---
    # Frases completas de boilerplate (mais específico que palavras soltas)
    boilerplate = re.compile(
        r'(feito\s+com|site\s+gr[aá]tis|comece\s+j[aá]|'
        r'image\s*\d+\s*:|alboom\s*pro|www\.alboom|'
        r'ir\s+para\s+o\s+topo|'
        r'p[aá]gina\s+inicial\s+de)',
        re.IGNORECASE,
    )
    nav_links = sorted(set(
        n for n in nav_links
        if not boilerplate.search(n)
    ))
    # Junta headings extraídos do raw (Fase 1) com os do texto limpo (Fase 2)
    all_headings = headings_raw + headings
    all_headings = sorted(set(
        h for h in all_headings
        if not boilerplate.search(h) and len(h.strip()) >= 5
    ))
    social = sorted(set(social))

    if not all_headings:
        return ""
    return '|'.join(all_headings)


def needs_selective_extract(url: str) -> bool:
    """Verifica se a URL precisa de extração seletiva (vs. hash do conteúdo bruto)."""
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in SELECTIVE_EXTRACT)


def fetch_via_jina(url: str, timeout: int = 30, verify_ssl: bool = True) -> str:
    """Busca o conteúdo via Jina Reader API (r.jina.ai). Retorna markdown limpo."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/markdown",
        "User-Agent": "Mozilla/5.0 (compatible; Monitor/1.0)",
    }
    resp = requests.get(jina_url, headers=headers, timeout=timeout, verify=verify_ssl)
    resp.raise_for_status()
    return resp.text


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

def _process_site_playwright(page, url: str) -> str:
    """Tenta obter conteúdo via Playwright. Levanta exceção se falhar."""
    html = fetch_html(page, url)
    if len(html) < 5000:
        raise ValueError(f"HTML muito pequeno ({len(html)} bytes)")
    content = extract_content(html, url)
    if not content or len(content) < 50:
        raise ValueError(f"Conteudo invalido ({len(content)} chars)")
    return content


def _process_site_jina(url: str) -> str:
    """Obtém conteúdo via Jina Reader. Levanta exceção se falhar."""
    content = fetch_via_jina(url)
    if not content or len(content) < 50:
        raise ValueError(f"Jina: conteudo invalido ({len(content)} chars)")
    return content


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
                    usar_jina = url in JINA_ONLY_SITES or any(
                        kw in url.lower() for kw in JINA_KEYWORDS
                    )
                    if usar_jina:
                        # Usa Jina Reader diretamente para sites problemáticos
                        content = _process_site_jina(url)
                        logging.info(f"OK {name} via Jina ({len(content)} chars)")
                    else:
                        try:
                            content = _process_site_playwright(page, url)
                            logging.info(f"OK {name} via Playwright ({len(content)} chars)")
                        except Exception as pw_err:
                            logging.warning(
                                f"Playwright falhou para {name}, "
                                f"tentando Jina Reader: {pw_err}"
                            )
                            content = _process_site_jina(url)
                            logging.info(f"OK {name} via Jina fallback ({len(content)} chars)")

                    # Extração seletiva para sites dinâmicos (ex: Alboom via Jina)
                    if needs_selective_extract(url):
                        raw_len = len(content)
                        content = extract_meaningful(content, url)
                        items = content.split('|') if content else []
                        logging.info(
                            f"Seletivo {name}: {raw_len} -> {len(content)} chars, "
                            f"{len(items)} itens"
                        )

                    results.append({
                        "url":   url,
                        "name":  name,
                        "hash":  calculate_hash(content),
                        "ok":    True,
                        "error": None,
                        # Debug: mostra o que foi extraído (truncado para 500 chars)
                        "preview": (content[:500] + "...") if len(content) > 500 else content,
                        "items":  len(content.split('|')) if content else 0,
                    })

                    time.sleep(2)

                except Exception as e:
                    logging.error(f"Erro em {name}: {e}")
                    results.append({
                        "url":    url,
                        "name":   name,
                        "hash":   None,
                        "ok":     False,
                        "error":  str(e),
                        "preview": "",
                        "items":  0,
                    })

        finally:
            context.close()
            browser.close()

    return results
