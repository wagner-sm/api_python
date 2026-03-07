import json
import logging
import time
import sys
import os
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

# =======================
# LOGGING (vai para stderr, não interfere no JSON)
# =======================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# =======================
# RETRY DECORATOR
# =======================
def com_retry(func, tentativas=3, espera=5, nome="operação"):
    """Executa func com retry em caso de exceção."""
    for i in range(tentativas):
        try:
            return func()
        except Exception as e:
            if i < tentativas - 1:
                logger.warning(f"[Retry {i+1}/{tentativas}] Falha em '{nome}': {e}. Aguardando {espera}s...")
                time.sleep(espera)
            else:
                logger.error(f"Todas as {tentativas} tentativas falharam em '{nome}': {e}")
                raise


class VaiPromoMonitor:
    URL = "https://www.vaidepromo.com.br/passagens-aereas/"
    TIMEOUT_PADRAO = 60_000   # ms
    TIMEOUT_CURTO  = 10_000   # ms

    def __init__(self):
        self.config = self.carregar_config()
        self.resultados = []

    # =======================
    # CONFIG — lê do stdin (enviado pelo app.py)
    # =======================
    def carregar_config(self):
        try:
            raw = sys.stdin.read()
            if not raw.strip():
                raise ValueError("stdin vazio — nenhuma configuração recebida")
            config = json.loads(raw)
            if "CONSULTAS" not in config or not config["CONSULTAS"]:
                raise ValueError("Config inválida: 'CONSULTAS' ausente ou vazia")
            logger.info(f"Configuração carregada: {len(config['CONSULTAS'])} consultas")
            return config
        except Exception as e:
            logger.error(f"Erro ao carregar configuração: {e}")
            # Retorna config vazia para não quebrar o fluxo
            return {"CONSULTAS": []}

    # =======================
    # HELPERS
    # =======================
    def trigger_change(self, page, selector):
        page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) {
                    ['input', 'change', 'blur'].forEach(ev =>
                        el.dispatchEvent(new Event(ev, { bubbles: true }))
                    );
                }
            }""",
            selector
        )

    def preencher_localizacao(self, page, campo, sigla):
        el = page.locator(f'[data-cy="{campo}"]')
        el.click()
        el.fill(sigla)
        page.wait_for_selector(
            f'[role="option"]:has-text("{sigla}")',
            timeout=self.TIMEOUT_CURTO
        )
        page.locator(f'[role="option"]:has-text("{sigla}")').first.click()
        self.trigger_change(page, f'[data-cy="{campo}"]')

    def clicar_como_humano(self, locator, page):
        locator.scroll_into_view_if_needed()
        locator.hover()
        page.wait_for_timeout(150)
        locator.click()
        page.wait_for_timeout(300)

    # =======================
    # CALENDÁRIO
    # =======================
    def selecionar_data(self, page, data_str):
        data = datetime.strptime(data_str, "%d/%m/%Y")
        data_cy = data.strftime("%d-%m-%Y")

        seletor_dia  = f'button[data-cy="{data_cy}"]'
        seletor_next = 'button[data-cy="data-range-picker-next"]'

        page.wait_for_selector(seletor_next, timeout=self.TIMEOUT_CURTO)

        for tentativa in range(24):
            dia = page.locator(seletor_dia)
            if dia.count() > 0:
                self.clicar_como_humano(dia.first, page)
                page.evaluate(
                    """(date) => {
                        const input = document.querySelector('[data-cy="departure-date"] input');
                        if (input) {
                            input.value = date;
                            ['input', 'change', 'blur'].forEach(ev =>
                                input.dispatchEvent(new Event(ev, { bubbles: true }))
                            );
                        }
                    }""",
                    data_str
                )
                logger.info(f"Data {data_str} selecionada após {tentativa+1} clique(s) no calendário")
                return

            page.locator(seletor_next).first.click()
            page.wait_for_timeout(600)

        raise Exception(f"Data {data_str} não encontrada no calendário após 24 tentativas")

    # =======================
    # AGUARDA RESULTADOS ESTÁVEIS
    # =======================
    def wait_for_results(self, page, timeout=30):
        start  = time.time()
        last   = 0
        stable = 0

        while time.time() - start < timeout:
            count = page.locator('div[class*="_content_"]').count()
            if count > 0 and count == last:
                stable += 1
                if stable >= 3:
                    logger.info(f"Resultados estabilizados: {count} card(s)")
                    return
            else:
                stable = 0
            last = count
            time.sleep(1)

        logger.warning(f"Timeout aguardando resultados (último count: {last})")

    # =======================
    # EXTRAÇÃO
    # =======================
    def extrair_voos(self, page):
        try:
            voos = page.evaluate(
                """() => {
                    const cards = document.querySelectorAll('div[class*="_content_"]');
                    const voos = [];

                    cards.forEach(card => {
                        const prices = [...card.querySelectorAll('strong')]
                            .map(s => s.textContent.trim())
                            .filter(t => t.includes('R$'))
                            .map(t => ({
                                text: t.replace(/\\u00a0/g, ' '),
                                value: parseFloat(
                                    t.replace(/[^0-9,]/g, '')
                                     .replace('.', '')
                                     .replace(',', '.')
                                )
                            }))
                            .filter(p => !isNaN(p.value));

                        if (!prices.length) return;

                        const final = prices.reduce((a, b) => a.value > b.value ? a : b);

                        const airline =
                            card.querySelector('img[alt]')?.alt ||
                            card.querySelector('span[class*="iata"]')?.textContent?.trim() ||
                            "Companhia não identificada";

                        voos.push({ companhia: airline, preco: final.text, valor: final.value });
                    });

                    const unique = {};
                    voos.forEach(v => { unique[v.companhia + v.valor] ||= v; });

                    return Object.values(unique).sort((a, b) => a.valor - b.valor);
                }"""
            )
            logger.info(f"Extraídos {len(voos)} voo(s)")
            return voos
        except Exception as e:
            logger.error(f"Erro ao extrair voos: {e}")
            return []

    # =======================
    # CONSULTA INDIVIDUAL (com retry)
    # =======================
    def _executar_consulta_interna(self, browser, consulta):
        """Uma tentativa de consulta — chamada pelo wrapper com retry."""
        page = browser.new_page()
        try:
            page.goto(self.URL, timeout=self.TIMEOUT_PADRAO)
            page.get_by_role("button", name="Só ida ou volta").click()

            self.preencher_localizacao(page, "departure", consulta["origem"])
            self.preencher_localizacao(page, "arrival",   consulta["destino"])

            page.get_by_role("textbox", name="Ida").nth(1).click()
            self.selecionar_data(page, consulta["data"])

            page.evaluate(
                """() => {
                    const form = document.querySelector('form');
                    form && form.dispatchEvent(new Event('submit', { bubbles: true }));
                }"""
            )

            page.wait_for_function(
                "() => location.href.includes('search') || "
                "document.querySelectorAll('div[class*=\"_content_\"]').length > 0",
                timeout=self.TIMEOUT_PADRAO
            )

            for _ in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)

            self.wait_for_results(page)
            voos = self.extrair_voos(page)
            url  = page.url

            return voos, url
        finally:
            page.close()

    def executar_consulta(self, browser, consulta):
        resultado = {
            "consulta":   consulta,
            "timestamp":  datetime.now().isoformat(),
            "voos":       []
        }

        try:
            voos, url = com_retry(
                lambda: self._executar_consulta_interna(browser, consulta),
                tentativas=3,
                espera=5,
                nome=f"{consulta['origem']}→{consulta['destino']}"
            )
            resultado["voos"] = voos
            resultado["url"]  = url

        except Exception as e:
            resultado["error"] = str(e)
            logger.error(f"Consulta falhou definitivamente: {consulta} — {e}")

        return resultado

    # =======================
    # RESUMO HTML para Telegram / n8n
    # =======================
    def resumo_telegram(self):
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

        linhas = [
            "✈️ <b>VaiPromo Monitor</b>",
            f"🕐 <i>Atualizado em {agora:%d/%m/%Y às %H:%M}</i>"
        ]

        for r in self.resultados:
            c = r["consulta"]
            linhas.append(
                f"\n<b>{html.escape(c['origem'])} → {html.escape(c['destino'])} "
                f"({html.escape(c['data'])})</b>"
            )

            if "error" in r:
                linhas.append(f"❌ {html.escape(r['error'])}")
                continue

            if not r["voos"]:
                linhas.append("⚠️ Nenhum voo encontrado")
                continue

            for i, v in enumerate(r["voos"][:3]):
                companhia = html.escape(v["companhia"])
                preco     = html.escape(v["preco"])
                if i == 0:
                    linhas.append(f"💰 <b>{companhia}</b> — {preco}")
                else:
                    linhas.append(f"#{i+1} {companhia} — {preco}")

            if "url" in r:
                linhas.append(f'🔗 <a href="{html.escape(r["url"])}">Ver no VaiPromo</a>')

        return "\n".join(linhas)

    # =======================
    # EXECUÇÃO PRINCIPAL
    # =======================
    def executar(self):
        if not self.config["CONSULTAS"]:
            logger.error("Sem consultas para executar. Abortando.")
            print(json.dumps({"resultados": [], "resumo": "❌ Nenhuma consulta configurada."}, ensure_ascii=False))
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                ],
            )

            try:
                for consulta in self.config["CONSULTAS"]:
                    logger.info(f"Iniciando: {consulta['origem']} → {consulta['destino']} - {consulta['data']}")
                    self.resultados.append(self.executar_consulta(browser, consulta))
            finally:
                browser.close()

        saida = {
            "resultados": self.resultados,
            "resumo":     self.resumo_telegram()
        }
        print(json.dumps(saida, ensure_ascii=False))
        logger.info("✅ Execução concluída!")


def main():
    VaiPromoMonitor().executar()


if __name__ == "__main__":
    main()
