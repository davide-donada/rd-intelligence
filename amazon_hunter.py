import os
import requests
from bs4 import BeautifulSoup
import mysql.connector
import random
import time
import json

DB_CONFIG = {
    'user': 'root',
    # Ora legge la variabile d'ambiente, se non c'è usa 'root' come fallback (ma fallirà)
    'password': os.getenv('DB_PASSWORD', 'password_finta_per_test_locale'), 
    'host': os.getenv('DB_HOST', '80.211.135.46'), # IP Server o 'mariadb' se siamo dentro Docker
    'port': 3306,
    'database': 'recensionedigitale'
}

# --- LISTA DI USER AGENT (Per non farci bloccare da Amazon) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
]

def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    
    # Headers rinforzati per sembrare un utente italiano vero
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    
    print(f"🕵️‍♂️  Analizzo ASIN: {asin}...")
    
    try:
        # Usiamo Session per mantenere i cookie (spesso aiuta coi prezzi corretti)
        session = requests.Session()
        response = session.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Bloccato (Status: {response.status_code})")
            return None
        
        soup = BeautifulSoup(response.content, "lxml")
        
        # 1. TITOLO
        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text(strip=True) if title_tag else "Titolo non trovato"
        
        # 2. PREZZO (STRATEGIA A CASCATA)
        # Cerchiamo in ordine di priorità:
        # A. Il prezzo "Da Pagare" (Offerta/Deal) -> È quello grosso
        # B. Il prezzo dentro la BuyBox (quello nel carrello)
        # C. Il prezzo "Core" generico
        
        price = 0.00
        found_price_text = None
        
        selectors = [
            'span.a-price.priceToPay span.a-offscreen',   # 1. Prezzo Offerta (Priorità assoluta)
            '#corePriceDisplay_desktop_feature_div span.a-price.priceToPay span.a-offscreen', # 1b. Alternativa Offerta
            '#corePrice_feature_div span.a-price span.a-offscreen', # 2. Prezzo Standard
            'span.a-price.a-text-price span.a-offscreen', # 3. Prezzo Listino (spesso è quello alto barrato, usiamo come fallback)
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                # Se troviamo un prezzo, ci fermiamo subito (per prendere il primo, cioè il migliore)
                # Ma scartiamo se il testo è vuoto
                if any(char.isdigit() for char in text):
                    found_price_text = text
                    print(f"   (Debug: Trovato prezzo con selettore '{selector}': {text})")
                    break
        
        if found_price_text:
            # Pulizia: "659,99 €" -> 659.99
            clean = found_price_text.replace("€", "").replace(".", "").replace(",", ".").strip()
            try:
                price = float(clean)
            except:
                print(f"⚠️ Errore conversione: {found_price_text}")

        # 3. IMMAGINE (Migliorata)
        img_url = ""
        img_tag = soup.find("img", {"id": "landingImage"})
        if img_tag:
            if img_tag.get("data-a-dynamic-image"):
                try:
                    json_imgs = json.loads(img_tag.get("data-a-dynamic-image"))
                    img_url = max(json_imgs.keys(), key=lambda k: json_imgs[k][0]) 
                except:
                    img_url = img_tag.get("src")
            else:
                img_url = img_tag.get("src")

        print(f"   ✅ Trovato: {title[:30]}...")
        print(f"   💰 Prezzo Finale: {price}€")
        
        return {
            "asin": asin,
            "title": title,
            "price": price,
            "image": img_url
        }

    except Exception as e:
        print(f"❌ Errore scraping: {e}")
        return None

def save_to_db(data):
    if not data: return

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Query che INSERISCE o AGGIORNA se esiste già
        query = """
        INSERT INTO products (asin, title, current_price, image_url, status)
        VALUES (%s, %s, %s, %s, 'draft')
        ON DUPLICATE KEY UPDATE 
            current_price = VALUES(current_price), 
            title = VALUES(title),
            image_url = VALUES(image_url),
            last_checked = NOW();
        """
        
        cursor.execute(query, (data['asin'], data['title'], data['price'], data['image']))
        conn.commit()
        print("💾 Dati salvati nel Database Remoto!")
        
    except mysql.connector.Error as err:
        print(f"❌ Errore DB: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    # TESTIAMO CON UNA MACCHINA CAFFÈ (De'Longhi Dedica)
    asin_da_testare = "B0CDCM3J5G" 
    
    dati = get_amazon_data(asin_da_testare)
    save_to_db(dati)