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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
}

def get_amazon_price(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, "html.parser")
        price_whole = soup.find('span', {'class': 'a-price-whole'})
        price_fraction = soup.find('span', {'class': 'a-price-fraction'})
        if price_whole:
            whole = price_whole.text.strip().replace('.', '').replace(',', '')
            fraction = price_fraction.text.strip() if price_fraction else "00"
            return float(f"{whole}.{fraction}")
    except: pass
    return None

def update_prices_loop():
    print("📉 MONITORAGGIO PREZZI (Smart History Attivo)...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Prende tutti i prodotti pubblicati
        cursor.execute("SELECT id, asin, current_price FROM products WHERE status = 'published'")
        products = cursor.fetchall()
        
        print(f"   Trovati {len(products)} prodotti da controllare.")

        for p in products:
            p_id, asin, old_price = p
            old_price = float(old_price) if old_price else 0.0
            
            new_price = get_amazon_price(asin)
            
            if new_price and new_price > 0:
                # 1. Aggiorna SEMPRE il prezzo attuale sulla vetrina
                cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                
                # 2. Salva nello storico SOLO se il prezzo è cambiato
                if new_price != old_price:
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    diff = new_price - old_price
                    icon = "📉" if diff < 0 else "📈"
                    print(f"   {icon} {asin}: {old_price}€ -> {new_price}€")
                else:
                    # Prezzo stabile, non scriviamo nello storico per risparmiare spazio
                    pass

                conn.commit()
            
            time.sleep(random.uniform(5, 10)) # Pausa anti-ban
            
    except Exception as e: print(f"❌ Errore Loop: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    update_prices_loop()