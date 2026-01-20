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
    print("📉 AVVIO MONITORAGGIO PREZZI (Con Storico)...")
    
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
            print(f"   > Controllo: {asin} - {title[:20]}...")
            
            new_price = get_amazon_price(asin)
            
            if new_price and new_price > 0:
                # 1. Aggiorna Tabella Principale
                cursor.execute("UPDATE products SET current_price = %s, last_update = NOW() WHERE id = %s", (new_price, p_id))
                
                # 2. Inserisci nello Storico (Logghiamo il prezzo per i grafici futuri)
                # Ottimizzazione: Salviamo nello storico solo se il prezzo è cambiato o se l'ultima rilevazione è vecchia di 24h?
                # Per semplicità ora salviamo SEMPRE, così popoli il grafico velocemente.
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                
                conn.commit()
                
                diff = new_price - float(old_price)
                if diff < 0:
                    print(f"     📉 CALO PREZZO! {old_price} -> {new_price} (-{abs(diff)}€)")
                elif diff > 0:
                    print(f"     📈 AUMENTO! {old_price} -> {new_price} (+{diff}€)")
                else:
                    print(f"     = Stabile a {new_price}€")
            
            # Pausa anti-ban
            time.sleep(random.uniform(5, 10))
            
    except Exception as e:
        print(f"❌ Errore Loop Prezzi: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    update_prices_loop()