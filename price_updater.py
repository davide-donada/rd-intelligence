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

def get_amazon_price(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "it-IT,it;q=0.9"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.content, "lxml")
        el = soup.select_one('span.a-price span.a-offscreen')
        if el:
            return float(el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip())
    except: pass
    return None

def update_prices_loop():
    while True:
        print(f"\n📉 [{datetime.now().strftime('%H:%M:%S')}] INIZIO GIRO DI CONTROLLO PREZZI...")
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id, asin, current_price FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            for p in products:
                p_id, asin, old_price = p
                new_price = get_amazon_price(asin)
                if new_price:
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    if abs(new_price - float(old_price)) > 0.01:
                        cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                        print(f"   💰 {asin}: CAMBIATO! {old_price}€ -> {new_price}€")
                    else:
                        print(f"   ⚖️ {asin}: Stabile a {new_price}€")
                    conn.commit()
                time.sleep(10) # Anti-ban
            print(f"✅ Giro completato su {len(products)} prodotti. Prossimo tra 10 minuti.")
            time.sleep(600) # 10 minuti
        except Exception as e:
            print(f"❌ Errore: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    from datetime import datetime
    update_prices_loop()