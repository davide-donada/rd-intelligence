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
        # 1. Recupera il post
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        if resp.status_code != 200: return
        
        post_data = resp.json()
        content = post_data['content']['raw']
        original_content = content
        
        new_str_dot = f"{new_price:.2f}"
        
        # --- CALCOLO VARIAZIONE PER ETICHETTA ---
        diff = new_price - float(old_price)
        if diff < 0:
            label_text = f"📉 Ribasso di € {abs(diff):.2f}"
            label_color = "#10b981" # Verde (cosa buona)
        else:
            label_text = f"📈 Rialzo di € {abs(diff):.2f}"
            label_color = "#ef4444" # Rosso (cosa cattiva)

        # HTML del blocco prezzo corretto (per ricostruzione totale)
        clean_price_html = f"<p style='font-size:1.8rem; color:#B12704; margin-bottom:5px;'><strong>€ {new_str_dot}</strong></p>"

        # --- AGGIORNAMENTO PREZZO (Logica V6 Safe) ---
        pattern_std = r"(<p[^>]*color:\s?#B12704[^>]*>\s*<strong>\s*€\s?)([\d\.,]+)(\s*</strong>\s*</p>)"
        pattern_fix = r"(<p[^>]*color:\s?#B12704[^>]*>\s*<strong>)(.*?)(</strong>\s*</p>)"
        pattern_reconstruct = r"(</h2>\s*)([\s\S]*?)(\s*<div style=\"border-left)"

        if re.search(pattern_std, content, re.IGNORECASE):
            content = re.sub(pattern_std, f"\\g<1>{new_str_dot}\\g<3>", content, flags=re.IGNORECASE)
        elif re.search(pattern_fix, content, re.IGNORECASE):
            content = re.sub(pattern_fix, f"\\g<1>€ {new_str_dot}\\g<3>", content, flags=re.IGNORECASE)
        elif re.search(pattern_reconstruct, content, re.IGNORECASE):
            content = re.sub(pattern_reconstruct, f"\\g<1>\n{clean_price_html}\n\\g<3>", content, flags=re.IGNORECASE)

        # --- AGGIORNAMENTO ETICHETTA "Monitoraggio appena avviato" ---
        # Cerchiamo il tag <small> dentro il div del widget.
        # Regex: Cerca <small>Qualsiasi Cosa</small>
        # Sostituisce con: <small style="color: ...">📉 Ribasso di ...</small>
        
        label_pattern = r"(<small>)(.*?)(</small>)"
        
        # Per sicurezza, applichiamo questa modifica solo se siamo vicini al widget del prezzo
        # (Per evitare di cambiare altri <small> nel testo se ce ne fossero)
        # Ma dato che il tuo template è rigido, possiamo provare a sostituire il primo <small> che troviamo dopo il prezzo.
        
        # Strategia sicura: Cerchiamo specificamente "Monitoraggio appena avviato" O "Variazione"
        # Così non rompiamo altri testi.
        specific_label_pattern = r"(<small>)(Monitoraggio appena avviato\.|Variazione:.*?|📉.*?|📈.*?)(</small>)"
        
        if re.search(specific_label_pattern, content, re.IGNORECASE):
            print(f"      🏷️ Aggiorno etichetta: {label_text}")
            content = re.sub(specific_label_pattern, f"\\g<1>{label_text}\\g<3>", content, count=1, flags=re.IGNORECASE)
        else:
            print("      ⚠️ Etichetta <small> non trovata o formato diverso.")

        # --- FIX SCHEMA JSON ---
        json_pattern = r'("offers":\s*\{"@type":\s*"Offer",\s*)(.*?)(,\s*"priceCurrency")'
        content = re.sub(json_pattern, f'\\g<1>"price": "{new_str_dot}"\\g<3>', content)
        
        old_json_pattern = r'("price":\s?")([\d\.]+)(",)'
        if re.search(old_json_pattern, content):
            content = re.sub(old_json_pattern, f'\\g<1>{new_str_dot}\\g<3>', content)

        # Aggiornamento Data
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # 2. INVIO DATI
        if content != original_content: 
            update_data = {'content': content}
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
            
            if up_resp.status_code == 200:
                print(f"      ✨ WordPress Aggiornato (ID: {wp_post_id}) -> € {new_str_dot}")
            else:
                print(f"      ❌ Errore API: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica necessaria.")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO (V.7 DYNAMIC LABEL) AVVIATO...")
    
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