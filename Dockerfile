FROM selenium/standalone-chrome:120.0

USER root
WORKDIR /app

# Instalar Python e pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
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

# Expor porta
EXPOSE 5000

# Variáveis de ambiente para Selenium headless
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# Rodar aplicação
CMD ["python3", "app.py"]
