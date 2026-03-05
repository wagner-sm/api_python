from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
import base64
import os
from io import BytesIO

class SetlistFMScraperPlaywright:
    def __init__(self, username, headless=True):
        self.username = username
        self.all_shows = []
        self.browser = None
        self.page = None
        self.headless = headless
        
        # Dicionário de festivais
        self.festival_cities = {
            'Bangers': 'São Paulo',
            'Março Maldito': 'São Paulo',
            'Summer Breeze': 'São Paulo',
            'Armageddon': 'Joinville',
            'Setembro Negro': 'São Paulo',
            'Crossroads': 'Curitiba',
            'Genocide': 'Curitiba',
            'Overload': 'São Paulo',
            'Liberation': 'São Paulo',
            'Monsters of Rock': 'São Paulo',
            'Zoombie': 'Rio Negrinho',
            "Live 'N' Louder": 'São Paulo',
            'Guaru': 'Guarulhos',
            'Visions': 'São Paulo'
        }

    def setup_driver(self):
        try:
            self._playwright = sync_playwright().start()
            
            self.browser = self._playwright.chromium.launch(
                headless=self.headless,
                executable_path=os.environ.get("CHROME_BIN", "/usr/bin/chromium"),
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions',
                    '--window-size=1920,1080',
                ]
            )
            
            context = self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            self.page = context.new_page()
            
            print("✅ Playwright configurado com sucesso!")
            print(f"🎪 Dicionário de festivais carregado: {len(self.festival_cities)} festivais")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao configurar Playwright: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def identify_festival_city(self, local_text):
        if not local_text:
            return None
        
        for festival_name, city in self.festival_cities.items():
            if festival_name.lower() in local_text.lower():
                return city
        
        return None

    def extract_show_data(self, show_html):
        """Extrai dados de um show individual a partir do HTML"""
        try:
            show_data = {
                'Data': 'N/A',
                'Artista': 'N/A',
                'Local': 'N/A',
                'Cidade': 'N/A'
            }
            
            soup = BeautifulSoup(show_html, 'lxml')
            
            # Data
            date_block = soup.find('span', class_='smallDateBlock')
            if date_block:
                month_elem = date_block.find('strong', class_='text-uppercase')
                day_elem = date_block.find('strong', class_='big')
                year_elem = date_block.find('span')
                
                if month_elem and day_elem and year_elem:
                    month_name = month_elem.get_text().strip()
                    day = day_elem.get_text().strip()
                    year = year_elem.get_text().strip()
                    
                    months = {
                        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                    }
                    month_num = months.get(month_name, '01')
                    show_data['Data'] = f"{day.zfill(2)}/{month_num}/{year}"
            
            # Artista
            content_div = soup.find('div', class_='column content')
            if content_div:
                artist_strong = content_div.find('strong')
                if artist_strong:
                    show_data['Artista'] = artist_strong.get_text().strip()
            
            # Local e cidade
            subline = soup.find('span', class_='subline')
            if subline:
                location_span = subline.find('span')
                if location_span:
                    location_text = location_span.get_text().strip()
                    show_data['Local'] = location_text
                    
                    # Verifica se é um festival conhecido
                    festival_city = self.identify_festival_city(location_text)
                    if festival_city:
                        show_data['Cidade'] = festival_city
                    # Se não é festival, tenta extrair da string
                    elif ',' in location_text:
                        location_parts = [part.strip() for part in location_text.split(',')]
                        if len(location_parts) >= 2:
                            show_data['Local'] = location_parts[0]
                            show_data['Cidade'] = location_parts[1]
                    # Identifica cidades brasileiras conhecidas
                    else:
                        city_lower = location_text.lower()
                        if 'curitiba' in city_lower:
                            show_data['Cidade'] = 'Curitiba'
                        elif 'são paulo' in city_lower or 'sao paulo' in city_lower:
                            show_data['Cidade'] = 'São Paulo'
                        elif 'rio de janeiro' in city_lower or 'rio' in city_lower:
                            show_data['Cidade'] = 'Rio de Janeiro'
                        elif 'joinville' in city_lower:
                            show_data['Cidade'] = 'Joinville'
                        elif 'rio negrinho' in city_lower:
                            show_data['Cidade'] = 'Rio Negrinho'
            
            return show_data
            
        except Exception as e:
            return None

    def wait_for_page_load(self):
        try:
            self.page.wait_for_selector("li.setlist", timeout=15000)
            time.sleep(2)  # Aguarda AJAX estabilizar
            return True
        except PlaywrightTimeoutError:
            print("⏰ Timeout aguardando página carregar")
            return False

    def scrape_current_page(self):
        try:
            # Aguarda carregamento
            if not self.wait_for_page_load():
                return []
            
            # Encontra todos os elementos de setlist
            show_elements = self.page.query_selector_all("li.setlist")
            
            # Filtra apenas shows attended (não upcoming)
            attended_shows_html = []
            for element in show_elements:
                try:
                    html = element.inner_html()
                    if 'upcoming' not in html.lower():
                        attended_shows_html.append(html)
                except:
                    continue
            
            print(f"📋 Encontrados {len(attended_shows_html)} shows na página atual")
            
            # Extrai dados de cada show
            page_shows = []
            for html in attended_shows_html:
                show_data = self.extract_show_data(html)
                if show_data and show_data['Artista'] != 'N/A':
                    page_shows.append(show_data)
            
            return page_shows
            
        except Exception as e:
            print(f"❌ Erro ao coletar página atual: {e}")
            return []

    def click_next_page(self):
        try:
            print("🔍 Procurando botão 'próxima página'...")
            
            next_selectors = [
                "a[title*='next' i]",
                "a:has(.fa-chevron-right)",
                ".pager a:last-child"
            ]
            
            next_button = None
            
            for selector in next_selectors:
                try:
                    buttons = self.page.query_selector_all(selector)
                    for button in buttons:
                        if button.is_visible() and button.is_enabled():
                            classes = button.get_attribute('class') or ''
                            if 'disabled' not in classes.lower():
                                next_button = button
                                print(f"✅ Botão encontrado")
                                break
                    
                    if next_button:
                        break
                        
                except:
                    continue
            
            if not next_button:
                print("📚 Botão 'próxima página' não encontrado")
                return False
            
            # Scroll até o botão
            next_button.scroll_into_view_if_needed()
            time.sleep(1)
            
            print("🖱️ Clicando no botão...")
            
            try:
                next_button.click()
                print("✅ Clique executado")
                time.sleep(3)  # Aguarda AJAX
                return True
            except Exception as e:
                print(f"⚠️ Erro no clique: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Erro ao clicar em próxima página: {e}")
            return False

    def get_total_shows(self):
        try:
            page_text = self.page.content()
            match = re.search(r'(\d+)\s+attended', page_text, re.IGNORECASE)
            if match:
                total = int(match.group(1))
                print(f"📊 Total de shows no perfil: {total}")
                return total
            return None
        except:
            return None

    def scrape_all_shows(self):
        if not self.setup_driver():
            return []
        
        try:
            print(f"Iniciando coleta para usuário: {self.username}")
            
            # Acessa a página do usuário
            url = f"https://www.setlist.fm/attended/{self.username}"
            print(f"🌐 Acessando: {url}")
            
            self.page.goto(url)
            
            # Aguarda carregamento inicial
            print("⏳ Aguardando carregamento...")
            time.sleep(3)
            
            # Obtém total de shows
            total_shows = self.get_total_shows()
            
            page_number = 1
            consecutive_empty_pages = 0
            max_empty_pages = 3
            max_pages = 50  # Limite de segurança
            
            while consecutive_empty_pages < max_empty_pages and page_number <= max_pages:
                print(f"\n📄 === PÁGINA {page_number} ===")
                
                # Coleta shows da página atual
                page_shows = self.scrape_current_page()
                
                if page_shows:
                    # Verifica duplicatas
                    existing_shows = {(s['Artista'], s['Data'], s['Local']) for s in self.all_shows}
                    new_shows = [s for s in page_shows 
                               if (s['Artista'], s['Data'], s['Local']) not in existing_shows]
                    
                    if new_shows:
                        self.all_shows.extend(new_shows)
                        consecutive_empty_pages = 0
                        print(f"✅ Adicionados {len(new_shows)} shows únicos")
                        print(f"📊 Total coletado: {len(self.all_shows)}")
                        
                        if total_shows and len(self.all_shows) >= total_shows:
                            print(f"🎉 Todos os {total_shows} shows coletados!")
                            break
                    else:
                        consecutive_empty_pages += 1
                        print(f"⚠️ Shows duplicados ({consecutive_empty_pages}/{max_empty_pages})")
                else:
                    consecutive_empty_pages += 1
                    print(f"⚠️ Página vazia ({consecutive_empty_pages}/{max_empty_pages})")
                
                # Tenta ir para próxima página
                if not self.click_next_page():
                    print("📚 Fim da navegação")
                    break
                
                page_number += 1
                time.sleep(2)  # Pausa entre páginas
            
            print(f"\n🎉 Coleta finalizada!")
            print(f"📊 Total de shows coletados: {len(self.all_shows)}")
            
            return self.all_shows
            
        except Exception as e:
            print(f"❌ Erro durante a coleta: {e}")
            return self.all_shows
            
        finally:
            if self.browser:
                self.browser.close()
            if hasattr(self, '_playwright'):
                self._playwright.stop()
            print("🔒 Browser fechado")

    def generate_excel_base64(self):
        if not self.all_shows:
            return None

        df = pd.DataFrame(self.all_shows)

        # Remove duplicatas
        df = df.drop_duplicates(subset=['Artista', 'Data', 'Local'])

        # Ordena por data (mais recente primeiro)
        df['Data_Sort'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        df = df.sort_values('Data_Sort', ascending=False, na_position='last')
        df = df.drop('Data_Sort', axis=1)

        buffer = BytesIO()

        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:

            df.to_excel(writer, sheet_name='Todos os Shows', index=False)

            stats_data = {
                'Métrica': [
                    'Total de Shows',
                    'Artistas Únicos',
                    'Locais Únicos',
                    'Cidades Únicas',
                    'Festivais Identificados',
                    'Show Mais Recente',
                    'Show Mais Antigo',
                    'Método de Coleta'
                ],
                'Valor': [
                    len(df),
                    df['Artista'].nunique(),
                    df['Local'].nunique(),
                    df['Cidade'].nunique(),
                    len([s for s in self.all_shows 
                         if any(fest in s['Local'] for fest in self.festival_cities.keys())]),
                    df['Data'].iloc[0] if len(df) > 0 else 'N/A',
                    df['Data'].iloc[-1] if len(df) > 0 else 'N/A',
                    'Playwright'
                ]
            }

            pd.DataFrame(stats_data).to_excel(writer, sheet_name='Estatísticas', index=False)

            if len(df) > 0:
                top_artists = df['Artista'].value_counts().head(50)
                top_df = pd.DataFrame({
                    'Artista': top_artists.index,
                    'Quantidade de Shows': top_artists.values
                })
                top_df.to_excel(writer, sheet_name='Top Artistas', index=False)

            if len(df) > 0:
                shows_por_cidade = df['Cidade'].value_counts()
                cidade_df = pd.DataFrame({
                    'Cidade': shows_por_cidade.index,
                    'Quantidade de Shows': shows_por_cidade.values
                })
                cidade_df.to_excel(writer, sheet_name='Shows por Cidade', index=False)

            if len(df) > 0:
                df_temp = df.copy()
                df_temp['Ano'] = df_temp['Data'].str.split('/').str[2]
                shows_por_ano = df_temp['Ano'].value_counts().sort_index()
                ano_df = pd.DataFrame({
                    'Ano': shows_por_ano.index,
                    'Quantidade de Shows': shows_por_ano.values
                })
                ano_df.to_excel(writer, sheet_name='Shows por Ano', index=False)

            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)

        buffer.seek(0)

        return base64.b64encode(buffer.read()).decode()


def main():
    USERNAME = "wsmetal"
    HEADLESS = True

    scraper = SetlistFMScraperPlaywright(USERNAME, headless=HEADLESS)

    shows = scraper.scrape_all_shows()

    if not shows:
        print(json.dumps({
            "success": False,
            "message": "Nenhum show foi coletado"
        }))
        return

    file_base64 = scraper.generate_excel_base64()

    if not file_base64:
        print(json.dumps({
            "success": False,
            "message": "Erro ao gerar Excel"
        }))
        return

    result = {
        "success": True,
        "message": f"{len(shows)} shows coletados",
        "fileName": "setlistfm_completo.xlsx",
        "file": file_base64
    }
    print(json.dumps(result), flush=True)

if __name__ == "__main__":
    main()
