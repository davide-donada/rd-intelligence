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
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        soup = BeautifulSoup(resp.content, "lxml")
        price_el = soup.select_one('span.a-price span.a-offscreen')
        price_val = float(price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if price_el else None
        
        deal_type = None
        badge_area = soup.select_one('#apex_desktop, #dealBadge_feature_div')
        badge_text = badge_area.get_text().lower() if badge_area else ""

        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type
    except: return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    """
    Ritorna True se aggiornato, False se il post non esiste più su WordPress
    """
    if not wp_post_id or wp_post_id == 0: return True
    headers = get_wp_headers()
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        
        # --- LOGICA DI PULIZIA: Se il post è stato cancellato ---
        if resp.status_code == 404:
            print(f"      🗑️  Post ID {wp_post_id} non trovato su WP. Segnalazione per rimozione...")
            return False
        
        if resp.status_code != 200: return True
        
        content = resp.json()['content']['raw']
        original_content = content
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        
        status_text = deal_label if deal_label else (f"📉 Ribasso di € {abs(diff):.2f}" if diff < -0.01 else f"📈 Rialzo di € {abs(diff):.2f}" if diff > 0.01 else "⚖️ Prezzo Stabile")

        # Regex Chirurgiche
        price_pattern = r'(<(p|div)[^>]*(?:color:\s?#b12704|rd-price-box)[^>]*>)(.*?)(</\2>)'
        class_pattern = r'(class="rd-status-val"[^>]*>)(.*?)(</div>)'
        
        content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>', content, flags=re.IGNORECASE)
        if 'class="rd-status-val"' in content:
            content = re.sub(class_pattern, f'\\g<1>{status_text}\\g<3>', content, flags=re.IGNORECASE)
        
        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\1{new_str}\\3', content)

        if content != original_content: 
            requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            print(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str}")
        
        return True

    except Exception as e:
        print(f"      ❌ Errore API: {e}")
        return True

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO v11.2 (AUTO-CLEANUP) AVVIATO...")
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
                    # Chiamiamo l'aggiornamento e controlliamo se il post esiste
                    post_exists = update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal)
                    
                    u_conn = mysql.connector.connect(**DB_CONFIG)
                    u_curr = u_conn.cursor()
                    
                    if not post_exists:
                        # Se il post non esiste più, lo mettiamo in stato 'trash' nel DB
                        u_curr.execute("UPDATE products SET status = 'trash' WHERE id = %s", (p['id'],))
                        print(f"      ✅ ASIN {p['asin']} rimosso dal monitoraggio (Post eliminato).")
                    elif abs(float(p['current_price']) - new_price) > 0.01:
                        # Aggiornamento normale se il prezzo è cambiato
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