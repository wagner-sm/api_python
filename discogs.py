import requests
import openpyxl
from openpyxl.styles import Font
import base64
import json
from io import BytesIO

# Substitua por seu nome de usuário e token do Discogs
USERNAME = 'wsmetal'
TOKEN = ' LfVhsGlTXOsxwvUCUJmXBPBiQnQuJjzpkvHAAflk'

# Cabeçalhos para autentica?
headers = {
    'User-Agent': 'ExportDiscogsCollection/1.0',
    'Authorization': f'Discogs token={TOKEN}'
}

# Lista para armazenar os dados
colecao = []

page = 1
while True:
    print(f"Carregando página {page}...")
    url = f'https://api.discogs.com/users/{USERNAME}/collection/folders/0/releases?page={page}&per_page=100'
    response = requests.get(url, headers=headers)
    data = response.json()

    for item in data['releases']:
        release = item['basic_information']
        artist = ', '.join([a['name'] for a in release['artists']])
        title = release['title']
        year = release['year']        
        label = ', '.join([l['name'] for l in release['labels']])
        catno = ', '.join([l['catno'] for l in release['labels']])
        format_ = ', '.join([f['name'] for f in release['formats']])  
        
        colecao.append([artist, title, year, label, catno, format_])

    if data['pagination']['pages'] > page:
        page += 1
    else:
        break

# Ordenar a lista por artista
colecao.sort(key=lambda x: x[0].lower())  # x[0] ? artista

# Criar planilha Excel
wb = openpyxl.Workbook()
ws = wb.active
ws.title = 'Discogs Collection'

# Cabe?hos
ws.append(['Artista', 'Título', 'Ano', 'Label', 'CatNo', 'Formato'])
for cell in ws[1]:  
        cell.font = Font(bold=True) 

# Adicionar dados ordenados
for linha in colecao:
    ws.append(linha)

# 🔥 SALVAR EM MEMÓRIA (não em disco)
buffer = BytesIO()
wb.save(buffer)
buffer.seek(0)

# Converter para base64
file_base64 = base64.b64encode(buffer.read()).decode()

# Imprimir JSON para o n8n
print(json.dumps({
    "file": file_base64,
    "fileName": "discogs_colecao.xlsx"
}))