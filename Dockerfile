FROM python:3.11-slim
WORKDIR /app

# Instalar Chromium via apt — mesmo binário que funcionava com Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Verificar instalação
RUN chromium --version

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Playwright SEM baixar binário próprio — usa /usr/bin/chromium
RUN pip install playwright && playwright install-deps chromium

# Copiar scripts
COPY discogs.py .
COPY setlistfm.py .
COPY vai_promo.py .
COPY monitor.py .
COPY app.py .

# Variáveis de ambiente para apontar ao Chromium do sistema
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Expor porta
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Rodar Flask
CMD ["python", "app.py"]
