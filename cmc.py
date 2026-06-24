from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from pathlib import Path
import requests
import base64
import json
import pandas as pd
import os
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta


class CMCCuritibaScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.captcha_userid = os.getenv("CAPTCHA_USERID")
        self.captcha_apikey = os.getenv("CAPTCHA_APIKEY")
        self.data_inicio = None
        self.data_fim = None
        self.all_data = []
        self.headers = [
            "Codigo", "Iniciativa", "Tipo", "Ementa", "Estado",
            "Ultimo tramite", "Razao", "Localizacao atual", "Data de apresentacao"
        ]

    def _current_dir(self):
        return Path(__file__).parent

    def solve_captcha(self, imagem_path):
        with open(imagem_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read())
        url = "https://api.apitruecaptcha.org/one/gettext"
        data = {
            "userid": self.captcha_userid,
            "apikey": self.captcha_apikey,
            "data": str(encoded_string)[2:-1]
        }
        r = requests.post(url=url, json=data)
        return json.loads(r.text)

    def setup_browser(self):
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            executable_path=os.environ.get("CHROME_BIN", "/usr/bin/chromium"),
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def extract_all_pages(self, page):
        while True:
            print("Extraindo pagina...")
            row_elements = page.query_selector_all("tr")
            for row in row_elements:
                cell_elements = row.query_selector_all("td.reportColumn, th.reportColumn")
                row_data = [cell.inner_text().strip() for cell in cell_elements]
                if len(row_data) == len(self.headers):
                    self.all_data.append(row_data)

            next_button = page.query_selector("a:text('Próximo >>')")
            if next_button:
                next_button.click()
                page.wait_for_timeout(3000)
            else:
                break

    def _fechar_popups(self):
        """Fecha modais, banners de cookie, alertas e dialogs que possam bloquear a pagina."""
        # Fecha dialogs nativos (alert/confirm)
        try:
            dialog = self.page.wait_for_event("dialog", timeout=3000)
            dialog.dismiss()
            print("🔔 Dialog nativo fechado")
        except Exception:
            pass

        # Tenta fechar botoes comuns de popup/modal
        fechar_selectors = [
            "button:has-text('Fechar')",
            "a:has-text('Fechar')",
            ".close",
            "[aria-label='Fechar']",
            "[aria-label='Close']",
            "button:has-text('×')",
            "button[data-dismiss='modal']",
            ".modal .btn-close",
            ".modal button.close",
            ".cookie-btn",
            "#close-modal",
            # YouTube / video overlays
            ".ytmCuedOverlayHost",
            ".ytp-ce-covering-overlay",
            "[class*='Overlay'] button[aria-label*='Fechar']",
            "[class*='Overlay'] [class*='close']",
        ]
        for sel in fechar_selectors:
            try:
                el = self.page.locator(sel).first
                if el.is_visible(timeout=1000):
                    el.click()
                    print(f"🍪 Popup fechado: {sel}")
                    self.page.wait_for_timeout(500)
            except Exception:
                continue

        # Pressiona Escape algumas vezes para fechar modais de video/lightbox
        try:
            for _ in range(3):
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def run(self):
        try:
            self.setup_browser()

            print("🌐 Acessando curitiba.pr.leg.br...")
            self.page.goto("https://www.curitiba.pr.leg.br/", wait_until="networkidle")
            self.page.wait_for_timeout(3000)

            # Fecha popups/modais que possam estar bloqueando
            self._fechar_popups()

            # Clica no link que abre a pagina de pesquisa (popup ou nova aba)
            link = self.page.locator(
                "#docs-internal-guid-b831bbaa-7fff-1bf1-4c39-28fd9b355501"
            ).get_by_role("link").first

            try:
                with self.context.expect_page(timeout=15000) as page1_info:
                    link.click()
                page1 = page1_info.value
                print("✅ Pagina de pesquisa aberta (nova aba/popup)")
            except Exception:
                # Fallback: tenta como popup
                try:
                    with self.page.expect_popup(timeout=10000) as page1_info:
                        link.click()
                    page1 = page1_info.value
                    print("✅ Pagina de pesquisa aberta (popup)")
                except Exception:
                    # Ultimo fallback: navega diretamente no link
                    href = link.get_attribute("href")
                    if href:
                        page1 = self.context.new_page()
                        page1.goto(href)
                        print(f"✅ Navegado diretamente para: {href}")
                    else:
                        raise Exception("Nao foi possivel abrir a pagina de pesquisa")

            page1.wait_for_timeout(2000)

            # Resolver captcha
            max_attempts = 5
            attempts = 0
            solved = False

            while attempts < max_attempts and not solved:
                try:
                    captcha_image_path = self._current_dir() / "imageCaptcha.png"
                    page1.locator("td.formField img").screenshot(path=captcha_image_path)

                    imagem_colorida = Image.open(captcha_image_path)
                    imagem_preto_branco = imagem_colorida.convert("L")
                    imagem_preto_branco.save(captcha_image_path)

                    solucao = self.solve_captcha(captcha_image_path)
                    page1.locator("input#captcha").fill(solucao.get("result"))
                    page1.locator("input[name='logon_action'][value='Entrar']").click()
                    page1.wait_for_timeout(3000)

                    error_present = page1.locator("span[style='color:red']").is_visible()
                    if not error_present:
                        solved = True
                    else:
                        print("Captcha invalido. Tentando novamente...")
                except Exception as e:
                    print(f"Erro ao processar CAPTCHA: {e}")
                attempts += 1

            if not solved:
                raise Exception("Numero maximo de tentativas de captcha alcancado.")

            print("✅ CAPTCHA resolvido com sucesso!")

            # Preencher datas
            data_inicio_str = self.data_inicio.strftime("%d/%m/%Y")
            data_fim_str = self.data_fim.strftime("%d/%m/%Y")

            campo_inicio_selector = "#pro_protocolada"
            page1.click(campo_inicio_selector)
            page1.fill(campo_inicio_selector, data_inicio_str)

            campo_fim_selector = "#pro_protocolada1"
            page1.click(campo_fim_selector)
            page1.fill(campo_fim_selector, data_fim_str)

            page1.fill("#pro_pesquisa_textual", "itinerario")
            page1.locator("input[name='select_action'][value='Pesquisar']").click()
            page1.wait_for_timeout(5000)

            # Extrair dados
            self.extract_all_pages(page1)
            print(f"📊 Total de registros extraidos: {len(self.all_data)}")

            page1.close()

        finally:
            if hasattr(self, "context"):
                self.context.close()
            if hasattr(self, "browser"):
                self.browser.close()
            if hasattr(self, "_playwright"):
                self._playwright.stop()
            print("🔒 Browser fechado")

    def _excel_path(self):
        return self._current_dir() / "cmc_dados.xlsx"

    def merge_and_save(self):
        """Junta novos dados com planilha existente, remove duplicados e salva."""
        df_novo = pd.DataFrame(self.all_data, columns=self.headers)

        path = self._excel_path()
        if path.exists():
            df_existente = pd.read_excel(path, sheet_name="Dados CMC")
            df_final = pd.concat([df_existente, df_novo], ignore_index=True)
            df_final = df_final.drop_duplicates(subset=["Codigo"], keep="first")
            print(f"📄 Planilha existente: {len(df_existente)} registros")
            print(f"🆕 Novos: {len(df_novo)} | 📊 Total apos merge: {len(df_final)}")
        else:
            df_final = df_novo
            print(f"📄 Planilha nova criada com {len(df_final)} registros")

        self.df_final = df_final
        self._save_excel(df_final)

    def _save_excel(self, df):
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Dados CMC", index=False)

            stats_data = {
                "Metrica": [
                    "Total de Registros",
                    "Data Inicio",
                    "Data Fim",
                    "Ultima Atualizacao",
                    "Termo Pesquisado",
                    "Fonte"
                ],
                "Valor": [
                    len(df),
                    self.data_inicio.strftime("%d/%m/%Y"),
                    self.data_fim.strftime("%d/%m/%Y"),
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "itinerario",
                    "curitiba.pr.leg.br"
                ]
            }
            pd.DataFrame(stats_data).to_excel(writer, sheet_name="Estatisticas", index=False)

            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except Exception:
                            pass
                    worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)

        # Salvar em disco
        path = self._excel_path()
        with open(path, "wb") as f:
            f.write(buffer.getvalue())
        buffer.seek(0)

        self._file_base64 = base64.b64encode(buffer.read()).decode()

    def generate_excel_base64(self):
        return self._file_base64


def main():
    data_fim = datetime.now()
    data_inicio = data_fim - timedelta(days=30)

    scraper = CMCCuritibaScraper(headless=True)
    scraper.data_inicio = data_inicio
    scraper.data_fim = data_fim

    try:
        scraper.run()
    except Exception as e:
        print(json.dumps({
            "success": False,
            "message": str(e)
        }))
        return

    if not scraper.all_data:
        print(json.dumps({
            "success": False,
            "message": "Nenhum registro extraido"
        }))
        return

    scraper.merge_and_save()

    file_base64 = scraper.generate_excel_base64()
    if not file_base64:
        print(json.dumps({
            "success": False,
            "message": "Erro ao gerar Excel"
        }))
        return

    result = {
        "success": True,
        "message": f"{len(scraper.df_final)} registros totais ({len(scraper.all_data)} novos)",
        "fileName": "cmc_preposicoes.xlsx",
        "file": file_base64
    }
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()