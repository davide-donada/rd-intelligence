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

def update_wp_post_price(wp_post_id, old_price, new_price):
    """
    Aggiorna il contenuto del post su WP cercando il blocco HTML specifico del prezzo
    e forzandone l'aggiornamento, ignorando il vecchio valore.
    """
    if not wp_post_id or wp_post_id == 0: return
    
    headers = get_wp_headers()
    try:
        # 1. Recupera il post attuale
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers)
        if resp.status_code != 200: 
            print(f"      ❌ Errore API WP (Get): {resp.status_code}")
            return
        
        post_data = resp.json()
        content = post_data['content']['rendered']
        original_content = content
        
        # Formattazione prezzi
        new_str_comma = f"{new_price:.2f}".replace('.', ',') # Es: 104,02
        new_str_dot = f"{new_price:.2f}" # Es: 104.02
        
        # --- 2. SOSTITUZIONE CHIRURGICA (TARGET HTML) ---
        # Cerchiamo esattamente il tag <p> rosso generato dal publisher.
        # Regex che cerca: <p style='...color:#B12704...'><strong>€ [QUALSIASI COSA]</strong></p>
        
        pattern_header = r"(<p style='font-size:1\.8rem; color:#B12704; margin-bottom:5px;'><strong>€\s?)([\d\.,]+)(</strong></p>)"
        
        # Sostituiamo il gruppo 2 (il numero vecchio) con il nuovo prezzo
        # Usiamo il formato con punto (Amazon style) o virgola? Usiamo quello che preferisci (qui metto punto per coerenza col DB)
        content = re.sub(pattern_header, f"\\1{new_str_dot}\\3", content)
        
        # --- 3. Aggiornamento Data ---
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # --- 4. Fallback per il prezzo nello Schema JSON (invisibile ma utile per SEO) ---
        # Cerca: "price": "104.00" e sostituisce con "price": "104.02"
        schema_pattern = r'("price":\s?")([\d\.]+)(",)'
        content = re.sub(schema_pattern, f'\\1{new_str_dot}\\3', content)

        # 5. Push dell'aggiornamento
        if content != original_content: 
            update_data = {'content': content}
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
            if up_resp.status_code == 200:
                print(f"      ✨ WordPress Aggiornato (ID: {wp_post_id}) -> € {new_str_dot}")
                
                # --- AUTO-FLUSH CACHE (Trucco per forzare aggiornamento) ---
                # A volte basta salvare di nuovo per pulire la cache di WP
            else:
                print(f"      ❌ Errore salvataggio WP: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica HTML rilevata (Regex non ha trovato il blocco?).")

    except Exception as e:
        print(f"      ❌ Errore critico aggiornamento WP: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO PREZZI (Versione Chirurgica) AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            
            print(f"📊 Scansione di {len(products)} prodotti...")
            
            for p_id, asin, old_price, wp_id in products:
                new_price = get_amazon_price(asin)
                
                if new_price and abs(float(old_price) - new_price) > 0.01:
                    print(f"   💰 {asin}: CAMBIATO! €{old_price} -> €{new_price}")
                    
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    conn.commit()
                    
                    update_wp_post_price(wp_id, old_price, new_price)
                else:
                    print(f"   ⚖️ {asin}: Stabile (€{old_price})")
                
                time.sleep(15) 
                
            print(f"✅ Giro completato. Pausa 1 ora.")
            time.sleep(3600) 
            
        except Exception as e:
            print(f"❌ Errore monitor: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_price_monitor()