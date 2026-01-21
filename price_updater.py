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
    Aggiorna il contenuto del post su WP cercando specificamente il vecchio prezzo
    e sostituendolo con il nuovo, gestendo sia formati 100.00 che 100,00.
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
        original_content_len = len(content)
        
        # Preparazione stringhe prezzi (Nuovo)
        new_str_dot = f"{new_price:.2f}"        # 103.97
        new_str_comma = new_str_dot.replace('.', ',') # 103,97
        
        # Preparazione stringhe prezzi (Vecchio) - Convertiamo float in stringa
        old_float = float(old_price)
        old_str_dot = f"{old_float:.2f}"        # 105.06
        old_str_comma = old_str_dot.replace('.', ',') # 105,06
        
        # 2. STRATEGIA CHIRURGICA: Cerca e sostituisci il numero esatto
        # Tentativo A: Formato con virgola (comune in Italia/WP) -> "105,06"
        if old_str_comma in content:
            print(f"      🔧 Trovato formato virgola ({old_str_comma}), sostituisco...")
            content = content.replace(old_str_comma, new_str_comma)
            
        # Tentativo B: Formato con punto -> "105.06"
        elif old_str_dot in content:
            print(f"      🔧 Trovato formato punto ({old_str_dot}), sostituisco...")
            content = content.replace(old_str_dot, new_str_dot)
            
        # Tentativo C: Fallback generico (se il vecchio prezzo non si trova esattamente)
        else:
            print(f"      ⚠️ Vecchio prezzo esatto non trovato nel testo. Provo regex generica...")
            # Cerca pattern tipo "€ 105,06" o "€105.06"
            content = re.sub(r'€\s?\d+[\.,]\d{2}', f'€ {new_str_comma}', content)

        # 3. Aggiorna la data se presente (solo per articoli nuovi con layout avanzato)
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # 4. Push dell'aggiornamento solo se il contenuto è cambiato
        if len(content) != original_content_len or old_str_comma not in content: 
            update_data = {'content': content}
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
            if up_resp.status_code == 200:
                print(f"      ✨ WordPress Aggiornato con successo (ID: {wp_post_id})")
            else:
                print(f"      ❌ Errore salvataggio WP: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica effettuata al testo (prezzo non trovato?).")

    except Exception as e:
        print(f"      ❌ Errore critico aggiornamento WP: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO PREZZI AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Seleziona prodotti pubblicati
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            
            print(f"📊 Scansione di {len(products)} prodotti in corso...")
            
            for p_id, asin, old_price, wp_id in products:
                new_price = get_amazon_price(asin)
                
                # Controllo se il prezzo è valido e se è cambiato (soglia 1 centesimo)
                if new_price and abs(float(old_price) - new_price) > 0.01:
                    print(f"   💰 {asin}: CAMBIATO! €{old_price} -> €{new_price}")
                    
                    # 1. Aggiorna Database
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    conn.commit()
                    
                    # 2. Aggiorna WordPress (passando anche il vecchio prezzo per trovarlo!)
                    update_wp_post_price(wp_id, old_price, new_price)
                else:
                    print(f"   ⚖️ {asin}: Stabile (€{old_price})")
                
                time.sleep(15) # Pausa anti-ban
                
            print(f"✅ Giro completato. Prossimo controllo tra 1 ora.")
            time.sleep(3600) 
            
        except Exception as e:
            print(f"❌ Errore monitor: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_price_monitor()