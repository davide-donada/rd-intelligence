import mysql.connector
import requests
import time
import os
import random
from datetime import datetime
from bs4 import BeautifulSoup

# CONFIGURAZIONE DATABASE
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
            
    except Exception as e:
        print(f"⚠️ Errore scraping {asin}: {e}")
    return None

def update_prices_loop():
    print("📉 AVVIO MONITORAGGIO PREZZI (Smart History)...")
    
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Prendiamo tutti i prodotti pubblicati
        cursor.execute("SELECT id, asin, title, current_price FROM products WHERE status = 'published'")
        products = cursor.fetchall()
        
        print(f"   Trovati {len(products)} prodotti da controllare.")
        
        for p in products:
            p_id, asin, title, old_price = p
            # Convertiamo old_price in float per sicurezza (dal DB arriva come Decimal o float)
            old_price = float(old_price) if old_price else 0.0
            
            # print(f"   > Controllo: {asin}...") # Decommenta per debug verboso
            
            new_price = get_amazon_price(asin)
            
            if new_price and new_price > 0:
                # 1. Aggiorna SEMPRE il prezzo corrente sul sito (per averlo fresco in homepage)
                cursor.execute("UPDATE products SET current_price = %s, last_update = NOW() WHERE id = %s", (new_price, p_id))
                
                # 2. LOGICA SMART: Salva nello storico SOLO se il prezzo è cambiato
                if new_price != old_price:
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    
                    diff = new_price - old_price
                    if diff < 0:
                        print(f"     📉 CALO PREZZO! {asin}: {old_price}€ -> {new_price}€ (-{abs(diff):.2f}€)")
                    else:
                        print(f"     📈 AUMENTO! {asin}: {old_price}€ -> {new_price}€ (+{diff:.2f}€)")
                else:
                    # Prezzo invariato, non intaso lo storico
                    pass

                conn.commit()
            
            # Pausa breve anti-ban tra i prodotti
            time.sleep(random.uniform(5, 10))
            
    except Exception as e:
        print(f"❌ Errore Loop Prezzi: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    update_prices_loop()