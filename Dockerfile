FROM python:3.11-slim

WORKDIR /app

# Instalar dependências mínimas para Chromium e libs necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    wget unzip curl \
    fonts-liberation \
    libasound2 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 xdg-utils libu2f-udev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todos os scripts da aplicação
COPY discogs.py .
COPY setlistfm.py .
COPY app.py .

# Variáveis de ambiente
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PORT=5000

# Expor porta
EXPOSE 5000

# Healthcheck para EASYPANEL
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s CMD curl -f http://localhost:5000/ || exit 1

# Comando de inicialização (Flask deve escutar 0.0.0.0)
CMD ["python", "app.py"]
