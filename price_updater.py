import mysql.connector
import requests
import time
import os
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
    if not wp_post_id or wp_post_id == 0: return
    
    headers = get_wp_headers()
    try:
        # 1. Recupera il post (raw content)
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        if resp.status_code != 200: return
        
        post_data = resp.json()
        content = post_data['content']['raw']
        original_content = content
        
        # Formattazione stringhe
        new_str_dot = f"{new_price:.2f}"        # 432.61
        new_str_comma = new_str_dot.replace('.', ',') # 432,61
        
        old_str_dot = f"{float(old_price):.2f}" # 432.64
        old_str_comma = old_str_dot.replace('.', ',') # 432,64
        
        print(f"      🔎 Cerco vecchio prezzo: {old_str_dot} o {old_str_comma}")

        # --- STRATEGIA 1: REGEX STRUTTURALE (Case Insensitive) ---
        # Cerca il blocco rosso tipico, ma ignorando maiuscole/minuscole nel colore
        pattern = r"(<p[^>]*color:\s?#B12704[^>]*>\s*<strong>\s*€\s?)([\d\.,]+)(\s*</strong>\s*</p>)"
        
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            print("      🔧 Strategia 1 (Regex HTML) attivata.")
            content = re.sub(pattern, f"\\1{new_str_dot}\\3", content, flags=re.IGNORECASE)
        else:
            # --- STRATEGIA 2: SOSTITUZIONE DIRETTA (BRUTE FORCE) ---
            print("      ⚠️ HTML cambiato, passo a Strategia 2 (Sostituzione Diretta).")
            
            # Cerca il vecchio numero esatto nel testo e cambialo
            # Nota: Sostituiamo solo se troviamo il numero esatto per evitare danni
            if old_str_comma in content:
                print(f"      🔧 Trovato {old_str_comma}, sostituisco con {new_str_comma}")
                content = content.replace(old_str_comma, new_str_comma)
            elif old_str_dot in content:
                print(f"      🔧 Trovato {old_str_dot}, sostituisco con {new_str_dot}")
                content = content.replace(old_str_dot, new_str_dot)
            else:
                print(f"      ❌ IMPOSSIBILE TROVARE IL VECCHIO PREZZO NEL TESTO.")

        # Aggiornamento Data (Funziona sempre)
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # Aggiornamento Schema JSON (Invisibile)
        schema_pattern = r'("price":\s?")([\d\.]+)(",)'
        content = re.sub(schema_pattern, f'\\1{new_str_dot}\\3', content)

        # 2. INVIO DATI SE CAMBIATO
        if content != original_content: 
            update_data = {'content': content}
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
            
            if up_resp.status_code == 200:
                print(f"      ✨ WordPress Aggiornato (ID: {wp_post_id}) -> € {new_str_dot}")
                
                # Verifica Immediata
                check_resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
                final_content = check_resp.json()['content']['raw']
                if new_str_dot in final_content or new_str_comma in final_content:
                     print(f"      ✅ VERIFICA OK: Prezzo presente nel DB.")
                else:
                     print(f"      💀 VERIFICA FALLITA.")
            else:
                print(f"      ❌ Errore API: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica necessaria (Il testo contiene già il nuovo prezzo?)")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO (V.CARRO ARMATO) AVVIATO...")
    
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
                    
                    # Passiamo il vecchio prezzo per permettere la ricerca "Brute Force"
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