import mysql.connector
import requests
import time
import os
import random
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE ---
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

def get_amazon_price(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, "lxml")
        
        # Usiamo gli stessi selettori di amazon_hunter
        selectors = ['span.a-price.priceToPay span.a-offscreen', '#corePrice_feature_div span.a-price span.a-offscreen', 'span.a-price span.a-offscreen']
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                price_str = el.get_text(strip=True).replace("€", "").replace(".", "").replace(",", ".").strip()
                return float(price_str)
    except: pass
    return None

def update_prices_loop():
    print("📉 MONITORAGGIO PREZZI AVVIATO...")
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id, asin, current_price FROM products WHERE status = 'published'")
            products = cursor.fetchall()

            for p in products:
                p_id, asin, old_price = p
                new_price = get_amazon_price(asin)

                if new_price and new_price > 0:
                    old_price = float(old_price) if old_price else 0.0
                    
                    # Aggiorna Database
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    
                    # Salva nello storico (Solo se il prezzo è cambiato)
                    if abs(new_price - old_price) > 0.01:
                        cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                        print(f"   💰 {asin}: AGGIORNATO {old_price}€ -> {new_price}€")
                    else:
                        print(f"   ⚖️ {asin}: Prezzo stabile ({new_price}€)")
                    
                    conn.commit()
                
                time.sleep(random.uniform(10, 20)) # Pausa per non essere bannati

            print("✅ Giro di controllo completato. Attendo 1 ora...")
            time.sleep(3600) # Controlla ogni ora

        except Exception as e:
            print(f"❌ Errore: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    update_prices_loop()