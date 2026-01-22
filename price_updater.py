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

def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        soup = BeautifulSoup(resp.content, "lxml")
        price_el = soup.select_one('span.a-price span.a-offscreen')
        price_val = float(price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if price_el else None
        
        deal_type = None
        txt = soup.get_text().lower()
        if "black friday" in txt: deal_type = "🖤 Offerta Black Friday"
        elif "offerta a tempo" in txt or soup.select_one('.a-badge-label'): deal_type = "⚡ Offerta a Tempo"
        
        return price_val, deal_type
    except: return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return
    headers = get_wp_headers()
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        if resp.status_code != 200: return
        content = resp.json()['content']['raw']
        original_content = content
        
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        
        if deal_label:
            status_text = deal_label
        elif diff < -0.01:
            status_text = f"📉 Ribasso di € {abs(diff):.2f}"
        elif diff > 0.01:
            status_text = f"📈 Rialzo di € {abs(diff):.2f}"
        else:
            status_text = "⚖️ Prezzo Stabile"

        # HTML del box da iniettare se manca (ora con classe unica)
        label_html = f'''\n<div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
<div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
<div class="rd-status-val" style="font-size: 0.8rem; color: #555;">{status_text}</div>
</div>'''

        # --- 1. AGGIORNAMENTO PREZZO ---
        # Pattern chirurgico per il prezzo: cerca rd-price-box o il colore rosso
        price_pattern = r'(<(p|div)[^>]*(?:color:\s?#b12704|rd-price-box)[^>]*>)(.*?)(</\2>)'
        content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>', content, flags=re.IGNORECASE)

        # --- 2. AGGIORNAMENTO ETICHETTA (Anti-Doppione) ---
        # Se esiste la classe specifica rd-status-val, usiamo quella (precisione 100%)
        if 'class="rd-status-val"' in content:
            content = re.sub(r'(class="rd-status-val"[^>]*>)(.*?)(</div>)', f'\\g<1>{status_text}\\g<3>', content, flags=re.IGNORECASE)
        
        # Altrimenti, se c'è il box grigio vecchio/corrotto, lo ripariamo
        elif "background: #6c757d1a" in content:
            # Ripariamo l'intestazione (se era diventata "Ribasso")
            content = re.sub(r'(uppercase; font-size: 0.85rem;">)(.*?)(</div>)', f'\\g<1>Stato Offerta\\g<3>', content, count=1, flags=re.IGNORECASE)
            # Aggiorniamo solo il secondo div (il valore)
            content = re.sub(r'(font-size: 0.8rem; color: #555;">)(.*?)(</div>)', f'\\g<1>{status_text}\\g<3>', content, count=1, flags=re.IGNORECASE)
        
        # Se non c'è proprio il box, lo iniettiamo MA SENZA CANCELLARE IMMAGINI
        else:
            # Cerchiamo il prezzo. Se dopo il prezzo c'è un'immagine, NON iniettiamo nulla per sicurezza in questo giro.
            # Inseriamo solo se subito dopo il prezzo NON c'è un tag img.
            check_match = re.search(price_pattern, content, re.IGNORECASE)
            if check_match:
                # Iniezione sicura subito dopo la chiusura del tag prezzo
                content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>{label_html}', content, count=1, flags=re.IGNORECASE)

        # --- 3. DATA E JSON ---
        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        
        # Fix JSON blindato
        json_pattern = r'("offers":\s*\{"@type":\s*"Offer",\s*)(.*?)(,\s*"priceCurrency")'
        content = re.sub(json_pattern, f'\\g<1>"price": "{new_str}"\\g<3>', content)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        # --- 4. INVIO ---
        if content != original_content: 
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            if up_resp.status_code == 200:
                print(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str} | {status_text}")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO v10.9 (SAFE & SURGICAL) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            conn.close()
            
            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                if new_price:
                    is_changed = abs(float(p['current_price']) - new_price) > 0.01
                    if is_changed or deal:
                        update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal)
                        
                        if is_changed:
                            print(f"   💰 {p['asin']}: CAMBIATO! €{p['current_price']} -> €{new_price}")
                            u_conn = mysql.connector.connect(**DB_CONFIG)
                            u_curr = u_conn.cursor()
                            u_curr.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p['id'], new_price))
                            u_curr.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p['id']))
                            u_conn.commit()
                            u_conn.close()
                time.sleep(15)
            time.sleep(3600)
        except Exception as e:
            print(f"❌ Errore: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_price_monitor()