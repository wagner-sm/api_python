FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema se necessário
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar scripts e app
COPY discogs.py .
COPY setlistfm.py .
COPY app.py .

# Expor porta
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# Rodar aplicação
CMD ["python", "app.py"]
