import mysql.connector
import requests
import time
import os
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime
import base64

# --- CONFIGURAZIONE ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def get_amazon_price(asin):
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None
        soup = BeautifulSoup(resp.content, "lxml")
        price_el = soup.select_one('span.a-price span.a-offscreen')
        if price_el:
            price_str = price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
            return float(price_str)
    except Exception as e:
        print(f"   ⚠️ Errore scraping ASIN {asin}: {e}")
    return None

def update_wp_post_price(wp_post_id, new_price):
    """Aggiorna il contenuto del post su WP per riflettere il nuovo prezzo"""
    if not wp_post_id or wp_post_id == 0: return
    
    headers = get_wp_headers()
    try:
        # 1. Recupera il post attuale
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers)
        if resp.status_code != 200: return
        
        post_data = resp.json()
        content = post_data['content']['rendered']
        
        # 2. Sostituzione del prezzo nel widget (cerchiamo il pattern € XX.XX)
        # Questa regex cerca il prezzo dentro il tuo template HTML
        updated_content = re.sub(r'€\s?\d+[\.,]\d{2}', f'€ {new_price:.2f}', content)
        
        # 3. Push dell'aggiornamento
        update_data = {'content': updated_content}
        requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
        print(f"      ✨ WordPress Aggiornato (ID: {wp_post_id})")
    except Exception as e:
        print(f"      ❌ Errore aggiornamento WP: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO PREZZI AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Seleziona solo i prodotti già pubblicati
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            
            print(f"📊 Scansione di {len(products)} prodotti in corso...")
            
            for p_id, asin, old_price, wp_id in products:
                new_price = get_amazon_price(asin)
                
                if new_price and abs(float(old_price) - new_price) > 0.01:
                    print(f"   💰 {asin}: CAMBIATO! €{old_price} -> €{new_price}")
                    
                    # Aggiorna Database
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    conn.commit()
                    
                    # Aggiorna l'articolo su WordPress
                    update_wp_post_price(wp_id, new_price)
                else:
                    print(f"   ⚖️ {asin}: Stabile (€{old_price})")
                
                time.sleep(15) # Pausa per non essere bannati da Amazon
                
            print(f"✅ Giro completato. Prossimo controllo tra 1 ora.")
            time.sleep(3600) # Attendi 1 ora
            
        except Exception as e:
            print(f"❌ Errore monitor: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_price_monitor()