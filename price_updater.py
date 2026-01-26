import mysql.connector
import requests
import time
import os
import re
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import base64
import json

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
AMAZON_TAG = "recensionedi-21" 

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def get_amazon_data(asin):
    # Link con TAG (Stabile)
    url = f"https://www.amazon.it/dp/{asin}?tag={AMAZON_TAG}&th=1&psc=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        
        soup = BeautifulSoup(resp.content, "lxml")
        
        # Selettore prezzo
        price_el = soup.select_one('span.a-price span.a-offscreen') or soup.select_one('.a-price .a-offscreen')
        price_val = float(price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if price_el else None
        
        # Rilevamento Deal
        deal_type = None
        badge_el = soup.select_one('#apex_desktop')
        badge_text = badge_el.get_text().lower() if badge_el else ""
        
        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type
    except: return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return True
    headers = get_wp_headers()
    
    try:
        # 1. GET: Leggiamo il post
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers, timeout=20)
        
        if resp.status_code == 404:
            log(f"      🗑️  Post WP #{wp_post_id} non trovato (404).")
            return False 

        if resp.status_code == 200:
            post_data = resp.json()
            if post_data.get('status') == 'trash':
                log(f"      🗑️  Post WP #{wp_post_id} è nel cestino (Status: Trash).")
                return False

        if resp.status_code != 200: 
            return True 
            
        content = post_data['content']['raw']
        original_content = content
        
        # --- PULIZIA PROFONDA (DEEP CLEAN) ---
        
        # 1. Rimuove il vecchio blocco "PREZZO STANDARD" con bordo sinistro solido (quello dell'esempio buggato)
        # Cerca un div che ha "border-left: 4px solid" e contiene "PREZZO STANDARD" o "Monitoraggio"
        content = re.sub(r'<div[^>]*border-left:\s*4px\s*solid[^>]*>.*?(PREZZO STANDARD|Monitoraggio).*?</div>', '', content, flags=re.DOTALL | re.IGNORECASE)

        # 2. Rimuove eventuali prezzi "nudi" (non nel box nuovo) che potrebbero essere rimasti
        # Cerca paragrafi con stile rosso tipico dei prezzi vecchi ma fuori dal box rd-price-box
        content = re.sub(r'<p[^>]*color:\s*#b12704[^>]*>.*?</p>', '', content, flags=re.DOTALL | re.IGNORECASE)

        # 3. Rimuove duplicati dei box "Stato Offerta" (sfondo grigio chiaro)
        content = re.sub(r'<div[^>]*background:\s*#6c757d1a[^>]*>.*?Stato Offerta.*?</div>\s*(<div[^>]*>.*?</div>\s*)*</div>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<div[^>]*background:\s*#6c757d1a[^>]*>.*?Monitoraggio avviato.*?</div>', '', content, flags=re.DOTALL | re.IGNORECASE)

        # Preparazione Dati
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        status_text = deal_label if deal_label else (f"📉 Ribasso di € {abs(diff):.2f}" if diff < -0.01 else (f"📈 Rialzo di € {abs(diff):.2f}" if diff > 0.01 else "⚖️ Prezzo Stabile"))

        label_html = f'''\n<div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
<div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
<div class="rd-status-val" style="font-size: 0.8rem; color: #555;">{status_text}</div>
</div>'''

        # --- AGGIORNAMENTO FLEXBOX ---
        # Cerchiamo il div specifico del nuovo layout
        price_regex = r'(<div class="rd-price-box"[^>]*>)(.*?)(</div>)' 
        
        if re.search(price_regex, content):
            # Aggiorna il numero
            content = re.sub(price_regex, f'\\g<1>€ {new_str}\\g<3>', content)
            # Inserisce il box stato SUBITO DOPO il prezzo
            content = re.sub(price_regex, f'\\g<0>{label_html}', content, count=1)
        else:
            # Se NON trova il layout Flexbox (caso raro ormai), prova a salvare il salvabile
            # Ma dato che stiamo pulendo aggressivamente, è meglio non fare fallback strani che creano doppi prezzi.
            # Se non c'è il box rd-price-box, logghiamo un warning e non tocchiamo per evitare danni.
            log(f"      ⚠️ Layout Flexbox non trovato per ID {wp_post_id}. Salto aggiornamento grafico per sicurezza.")
            # Aggiorniamo solo i metadati JSON-LD e data in fondo
            pass

        # Aggiorna Data e Schema (sempre)
        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            # 2. POST: Inviamo aggiornamento
            update_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            
            if update_resp.status_code in [400, 401, 403]:
                try:
                    err_json = update_resp.json()
                    err_msg = err_json.get('message', '').lower()
                    if 'cestino' in err_msg or 'trash' in err_msg or 'rest_cannot_edit' in err_json.get('code', ''):
                        log(f"      🗑️  Errore WP: Post #{wp_post_id} nel cestino.")
                        return False
                except: pass

            if update_resp.status_code == 200:
                log(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str}")
            else:
                log(f"      ⚠️ Errore Update WP: {update_resp.status_code}")
        
        return True

    except Exception as e:
        log(f"      ❌ Errore Critico WP API: {e}")
        return True

def run_price_monitor():
    log("🚀 MONITORAGGIO v15.3 (DEEP CLEAN) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            conn.close()
            
            log(f"📊 Scansione {len(products)} prodotti...")
            
            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                
                if new_price:
                    post_exists = update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal)
                    
                    if not post_exists:
                        conn = mysql.connector.connect(**DB_CONFIG)
                        cur = conn.cursor()
                        cur.execute("UPDATE products SET status = 'trash' WHERE id = %s", (p['id'],))
                        conn.commit()
                        conn.close()
                        log(f"      🚫 ASIN {p['asin']} rimosso (Post Cestinato).")
                        continue 
                    
                    if abs(float(p['current_price']) - new_price) > 0.01:
                        conn = mysql.connector.connect(**DB_CONFIG)
                        cur = conn.cursor()
                        cur.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p['id']))
                        cur.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p['id'], new_price))
                        conn.commit()
                        conn.close()
                        log(f"      💰 CAMBIO: {p['asin']} -> € {new_price}")
                    else:
                        log(f"   ⚖️  {p['asin']} Stabile (€ {p['current_price']})")
                
                time.sleep(15)
            
            log(f"✅ Giro completato. Pausa 1 ora.")
            time.sleep(3600)
            
        except Exception as e:
            log(f"❌ Errore critico nel loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_price_monitor()