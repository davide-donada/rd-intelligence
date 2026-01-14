import requests
from bs4 import BeautifulSoup
import mysql.connector
import random
import time
import json
import os

# --- CONFIGURAZIONE DATABASE ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'), 
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15"
]

def get_amazon_data(asin):
    # ... (La funzione get_amazon_data resta UGUALE a prima, non serve cambiarla) ...
    # Se vuoi risparmiare spazio qui, lascia la versione che avevi già funzionante.
    # Per sicurezza te la rimetto sintetica:
    url = f"https://www.amazon.it/dp/{asin}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Connection": "keep-alive"
    }
    
    print(f"🕵️‍♂️  Analizzo ASIN: {asin}...")
    try:
        session = requests.Session()
        response = session.get(url, headers=headers)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.content, "lxml")
        title = soup.find("span", {"id": "productTitle"}).get_text(strip=True) if soup.find("span", {"id": "productTitle"}) else "Titolo non trovato"
        
        # Logica Prezzo
        price = 0.00
        selectors = ['span.a-price.priceToPay span.a-offscreen', '#corePrice_feature_div span.a-price span.a-offscreen', 'span.a-price.a-text-price span.a-offscreen']
        for sel in selectors:
            el = soup.select_one(sel)
            if el and any(c.isdigit() for c in el.get_text()):
                clean = el.get_text(strip=True).replace("€", "").replace(".", "").replace(",", ".").strip()
                try: price = float(clean); break
                except: pass
        
        # Logica Immagine
        img_url = ""
        img_tag = soup.find("img", {"id": "landingImage"})
        if img_tag:
            img_url = img_tag.get("src")
            if img_tag.get("data-a-dynamic-image"):
                try: img_url = max(json.loads(img_tag.get("data-a-dynamic-image")).keys(), key=lambda k: json.loads(img_tag.get("data-a-dynamic-image"))[k][0])
                except: pass

        return {"asin": asin, "title": title, "price": price, "image": img_url}
    except Exception as e:
        print(f"❌ Errore scraping: {e}")
        return None

# --- QUESTA È LA PARTE AGGIORNATA ---
def save_to_db(data):
    if not data: return

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Recuperiamo il testo AI se esiste, altrimenti None
        ai_content = data.get('ai_content', None)

        # Query aggiornata per includere 'ai_sentiment'
        query = """
        INSERT INTO products (asin, title, current_price, image_url, ai_sentiment, status)
        VALUES (%s, %s, %s, %s, %s, 'draft')
        ON DUPLICATE KEY UPDATE 
            current_price = VALUES(current_price), 
            title = VALUES(title),
            image_url = VALUES(image_url),
            ai_sentiment = VALUES(ai_sentiment),  -- Aggiorna anche l'AI se cambia
            last_checked = NOW();
        """
        
        cursor.execute(query, (data['asin'], data['title'], data['price'], data['image'], ai_content))
        conn.commit()
        print("💾 Dati (inclusa AI) salvati nel Database!")
        
    except mysql.connector.Error as err:
        print(f"❌ Errore DB: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()