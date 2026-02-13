FROM selenium/standalone-chrome:120.0

USER root
WORKDIR /app

# Instalar Python, pip e dependências necessárias para Chrome
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
    && rm -rf /var/lib/apt/lists/*

# Criar link simbólico para python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Copiar requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar scripts e app
COPY discogs.py .
COPY setlistfm.py .
COPY app.py .

# Configurar variáveis de ambiente para Chrome/Selenium
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Garantir permissões
RUN chmod -R 755 /app

# Expor porta
EXPOSE 5000

# Rodar aplicação
CMD ["python3", "app.py"]
