# Usiamo un'immagine Python leggera
FROM python:3.9-slim

# Disabilita il buffering per vedere i log in tempo reale su Coolify
ENV PYTHONUNBUFFERED=1

# Creiamo la cartella di lavoro
WORKDIR /app

# Copiamo i requisiti e installiamo le librerie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamo tutto il codice
COPY . .

# Comando di avvio (Lancia il ciclo infinito)
CMD ["python", "main.py"]