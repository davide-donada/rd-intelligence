import mysql.connector
import requests
import time
import os
import re
from bs4 import BeautifulSoup
from datetime import datetime
import base64

# Configurazione DB e WP (Assicurati che le variabili d'ambiente siano su Coolify)
DB_CONFIG = {'user': 'root', 'password': os.getenv('DB_PASSWORD'), 'host': os.getenv('DB_HOST'), 'port': 3306, 'database': 'recensionedigitale'}
WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"

def get_wp_headers():
    token = base64.b64encode(f"{os.getenv('WP_USER')}:{os.getenv('WP_PASSWORD')}".encode())
    return {'Authorization': f'Basic {token.decode()}', 'Content-Type': 'application/json'}

def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.content, "lxml")
        
        # Prezzo
        p_el = soup.select_one('span.a-price span.a-offscreen')
        price = float(p_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if p_el else None
        
        # Eventi
        txt = soup.get_text().lower()
        deal = None
        if "black friday" in txt: deal = "🖤 Offerta Black Friday"
        elif "offerta a tempo" in txt or soup.select_one('.a-badge-label'): deal = "⚡ Offerta a Tempo"
        elif "prime day" in txt: deal = "🔵 Offerta Prime Day"
        
        return price, deal
    except: return None, None

def update_wp_post(wp_id, old_p, new_p, deal):
    headers = get_wp_headers()
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_id}?context=edit", headers=headers)
        content = resp.json()['content']['raw']
        orig = content
        
        new_s = f"{new_p:.2f}"
        diff = new_p - float(old_p)
        label = deal if deal else (f"📉 Ribasso di € {abs(diff):.2f}" if diff < -0.01 else f"📈 Rialzo di € {abs(diff):.2f}" if diff > 0.01 else "⚖️ Prezzo Stabile")

        # 1. Update Prezzo (P o DIV rossi) - Auto-riparazione contenuti corrotti
        p_pattern = r'(<(p|div)[^>]*color:\s?#b12704[^>]*>)(.*?)(</\2>)'
        content = re.sub(p_pattern, f'\\g<1>€ {new_s}\\g<4>', content, flags=re.IGNORECASE)

        # 2. Update Etichetta (Small o Div di stato)
        l_pattern = r'(<(small|div)[^>]*>)(Analisi in corso\.\.\.|Monitoraggio.*?|⚖️.*?|📉.*?|📈.*?|⚡.*?|🖤.*?)(</\2>)'
        content = re.sub(l_pattern, f'\\g<1>{label}\\g<4>', content, count=2, flags=re.IGNORECASE)

        # 3. Update JSON & Data
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\1{new_s}\\3', content)
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {datetime.now().strftime("%d/%m/%Y")}', content)

        if content != orig:
            requests.post(f"{WP_API_URL}/posts/{wp_id}", headers=headers, json={'content': content})
            print(f"      ✨ WP Aggiornato (ID: {wp_id}) -> € {new_s} | {label}")
    except Exception as e: print(f"      ❌ Errore WP: {e}")

def run_price_monitor():
    while True:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
        for p_id, asin, old_p, wp_id in cursor.fetchall():
            new_p, deal = get_amazon_data(asin)
            p_changed = new_p and abs(float(old_p) - new_p) > 0.01
            if p_changed or deal:
                if p_changed:
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_p, p_id))
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_p))
                    conn.commit()
                update_wp_post(wp_id, old_p, new_p if new_p else old_p, deal)
            time.sleep(15)
        conn.close()
        time.sleep(3600)

if __name__ == "__main__":
    run_price_monitor()