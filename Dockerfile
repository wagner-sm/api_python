FROM selenium/standalone-chrome:120.0

USER root
WORKDIR /app

# Instalar Python, pip e TODAS as dependências necessárias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libnss3 \
    libgconf-2-4 \
    libxi6 \
    libglib2.0-0 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    libappindicator3-1 \
    libnspr4 \
    libnss3 \
    libxss1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Criar link simbólico para python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Encontrar e configurar o ChromeDriver que vem com a imagem
RUN CHROMEDRIVER=$(find /opt -name "chromedriver" -type f 2>/dev/null | head -1) && \
    if [ -n "$CHROMEDRIVER" ]; then \
        ln -sf "$CHROMEDRIVER" /usr/local/bin/chromedriver && \
        chmod +x /usr/local/bin/chromedriver && \
        echo "ChromeDriver linked: $CHROMEDRIVER"; \
    else \
        echo "WARNING: ChromeDriver not found in /opt"; \
    fi

# Copiar requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar scripts e app
COPY discogs.py .
COPY setlistfm.py .
COPY app.py .

# Configurar variáveis de ambiente
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null
ENV SE_DRIVER_PATH=/usr/local/bin/chromedriver
ENV CHROME_BIN=/usr/bin/google-chrome

# Criar diretório para cache do Selenium e dar permissão
RUN mkdir -p /root/.cache/selenium && chmod -R 777 /root/.cache

# Garantir permissões
RUN chmod -R 755 /app

# Expor porta
EXPOSE 5000

# Rodar aplicação
CMD ["python3", "app.py"]
