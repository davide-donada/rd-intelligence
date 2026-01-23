import mysql.connector
import requests
import time
import os
import re
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
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

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def get_amazon_data(asin):
    # URL PULITO (No Affiliate) per non sporcare le statistiche
    url = f"https://www.amazon.it/dp/{asin}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        
        if resp.status_code == 503:
            log(f"      ⚠️  Amazon 503 (Busy) per {asin}")
            return None, None
        if resp.status_code != 200: 
            return None, None

        soup = BeautifulSoup(resp.content, "lxml")
        
        # 1. ISOLAMENTO AREA PRODOTTO (Espanso)
        # Cerchiamo nei container principali che racchiudono le info del prodotto
        product_area = soup.select_one('#centerCol') or soup.select_one('#ppd') or soup.select_one('#dp-container')
        
        if not product_area:
            # Se non troviamo l'area, probabilmente è un Robot Check
            if "api-services-support@amazon.com" in soup.get_text():
                log(f"      🤖  Robot Check rilevato per {asin}")
            else:
                log(f"      ❓  Area prodotto non trovata per {asin}")
            return None, None

        # 2. RICERCA PREZZO (Selettori in ordine di priorità)
        price_el = None
        
        # A. Prezzo standard (CorePrice)
        price_el = product_area.select_one('#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen')
        
        # B. Prezzo nel BuyBox (comune per pre-ordini o offerte particolari)
        if not price_el:
            price_el = product_area.select_one('#price_inside_buybox')
            
        # C. Prezzo nel blocco secondario
        if not price_el:
            price_el = product_area.select_one('#corePrice_feature_div span.a-price span.a-offscreen')
            
        # D. Ultimo tentativo generico nell'area centrale
        if not price_el:
            price_el = product_area.select_one('span.a-price span.a-offscreen')

        price_val = None
        if price_el:
            price_text = price_el.get_text().strip()
            try:
                # Pulizia: rimuove simboli e corregge virgole/punti
                clean_price = price_text.replace("€", "").replace(".", "").replace(",", ".").strip()
                price_val = float(clean_price)
            except ValueError:
                log(f"      ⚠️  Prezzo non convertibile: {price_text} per {asin}")
        else:
            log(f"      🔍  Prezzo non trovato nel HTML di {asin} (Area trovata)")
            return None, None
        
        # 3. RILEVAMENTO OFFERTE
        deal_type = None
        badge_area = product_area.select_one('#apex_desktop, .a-section.a-spacing-none.a-spacing-top-mini, #top_level_asins_contact_info_feature_div')
        badge_text = badge_area.get_text().lower() if badge_area else ""

        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type

    except Exception as e: 
        log(f"      ❌ Errore critico Amazon ({asin}): {e}")
        return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return True
    headers = get_wp_headers()
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers, timeout=20)
        if resp.status_code != 200: return True
        
        content = resp.json()['content']['raw']
        original_content = content
        
        # PULIZIA VECCHI BOX
        content = re.sub(r'<div[^>]*>.*?Monitoraggio appena avviato.*?</div>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<div[^>]*>.*?PREZZO STANDARD.*?</div>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<div[^>]*background:\s*#6c757d1a[^>]*>.*?Stato Offerta.*?</div>\s*(<div[^>]*>.*?</div>\s*)*</div>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<div class="rd-status-val".*?</div>', '', content, flags=re.DOTALL | re.IGNORECASE)

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

        label_html = f'''\n<div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
<div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
<div class="rd-status-val" style="font-size: 0.8rem; color: #555;">{status_text}</div>
</div>'''

        price_pattern = r'(<(p|div)[^>]*(?:color:\s?#b12704|rd-price-box)[^>]*>)(.*?)(</\2>)'
        content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>', content, flags=re.IGNORECASE)
        content = re.sub(price_pattern, f'\\g<0>{label_html}', content, count=1, flags=re.IGNORECASE)

        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            log(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str}")
        
        return True
    except Exception as e:
        log(f"      ❌ Errore API WP: {e}")
        return True

def run_price_monitor():
    log("🚀 MONITORAGGIO v13.1 (SNIPER PLUS) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            conn.close()
            
            log(f"📊 Inizio scansione di {len(products)} prodotti...")

            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                
                if new_price:
                    update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal)
                    
                    if abs(float(p['current_price']) - new_price) > 0.01:
                        u_conn = mysql.connector.connect(**DB_CONFIG)
                        u_curr = u_conn.cursor()
                        u_curr.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p['id']))
                        u_curr.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p['id'], new_price))
                        u_conn.commit()
                        u_conn.close()
                        log(f"      💰 CAMBIO: {p['asin']} -> € {new_price}")
                    else:
                        log(f"   ⚖️  {p['asin']} Stabile (€ {p['current_price']})")
                
                # Attesa casuale tra i prodotti
                time.sleep(random.uniform(15, 25)) 
            
            log(f"✅ Giro completato. Pausa 1 ora.")
            time.sleep(3600)
            
        except Exception as e:
            log(f"❌ Errore critico: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_price_monitor()