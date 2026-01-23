import mysql.connector
import requests as standard_requests # Per WordPress (standard)
from curl_cffi import requests as browser_requests # Per Amazon (simula Chrome)
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
    """
    Scarica i dati da Amazon simulando un browser reale.
    Usa selettori specifici per evitare prezzi di prodotti sponsorizzati.
    """
    url = f"https://www.amazon.it/dp/{asin}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }

    try:
        # Usa curl_cffi con impersonificazione Chrome
        resp = browser_requests.get(
            url, 
            headers=headers, 
            timeout=30, 
            impersonate="chrome120"
        )
        
        if resp.status_code == 503:
            log(f"      ⚠️  Amazon 503 (Blocco Temporaneo) per {asin}")
            return None, None
        
        if resp.status_code != 200: 
            log(f"      ⚠️  Status Code anomalo: {resp.status_code} per {asin}")
            return None, None
            
        soup = BeautifulSoup(resp.content, "lxml")
        
        # Check Anti-Bot/Captcha
        page_text = soup.get_text().lower()
        if "inserisci i caratteri" in page_text or "enter the characters" in page_text:
            log(f"      🤖  CAPTCHA rilevato per {asin} (Salto...)")
            return None, None

        # --- SELEZIONE PRECISA DEL PRODOTTO ---
        # Cerchiamo solo nella colonna centrale per evitare banner e sponsor
        product_area = soup.select_one('#centerCol') or soup.select_one('#ppd') or soup.select_one('#apex_desktop')
        search_area = product_area if product_area else soup

        # 1. Cerca nel box prezzo principale (Core Price)
        price_el = search_area.select_one('#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen')
        
        # 2. Fallback su altri box prezzo comuni
        if not price_el:
            price_el = search_area.select_one('#corePrice_feature_div span.a-price span.a-offscreen')
            
        # 3. Ultimo tentativo generico (ma sempre dentro l'area prodotto)
        if not price_el:
            price_el = search_area.select_one('span.a-price span.a-offscreen')

        # Estrazione Valore
        if price_el:
            raw_price = price_el.get_text().strip()
            clean_price = raw_price.replace("€", "").replace(".", "").replace(",", ".").strip()
            try:
                price_val = float(clean_price)
            except ValueError:
                log(f"      ⚠️  Errore conversione prezzo: '{raw_price}' per {asin}")
                price_val = None
        else:
            price_val = None
        
        # Deal Detection
        deal_type = None
        badge_area = search_area.select_one('#apex_desktop, .a-section.a-spacing-none.a-spacing-top-mini')
        badge_text = badge_area.get_text().lower() if badge_area else ""

        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type

    except Exception as e: 
        log(f"      ❌ Errore connessione Amazon: {e}")
        return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return True
    headers = get_wp_headers()
    try:
        # Usa requests standard per WordPress
        resp = standard_requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers, timeout=20)
        
        if resp.status_code == 404:
            log(f"      🗑️  Post ID {wp_post_id} non trovato. Segnalo rimozione...")
            return False
        
        if resp.status_code != 200: return True
        
        content = resp.json()['content']['raw']
        original_content = content
        
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        
        # Logica etichetta status
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

        # Regex Chirurgiche per aggiornamento HTML
        price_pattern = r'(<(p|div)[^>]*(?:color:\s?#b12704|rd-price-box)[^>]*>)(.*?)(</\2>)'
        content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>', content, flags=re.IGNORECASE)

        if 'class="rd-status-val"' in content:
            content = re.sub(r'(class="rd-status-val"[^>]*>)(.*?)(</div>)', f'\\g<1>{status_text}\\g<3>', content, flags=re.IGNORECASE)
        elif "Stato Offerta" in content:
            content = re.sub(r'(uppercase; font-size: 0.85rem;">)(.*?)(</div>)', f'\\g<1>Stato Offerta\\g<3>', content, count=1, flags=re.IGNORECASE)
            content = re.sub(r'(color: #555;">)(.*?)(</div>)', f'\\g<1>{status_text}\\g<3>', content, count=1, flags=re.IGNORECASE)
        else:
            content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>{label_html}', content, count=1, flags=re.IGNORECASE)

        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("offers":\s*\{"@type":\s*"Offer",\s*)(.*?)(,\s*"priceCurrency")', f'\\g<1>"price": "{new_str}"\\g<3>', content)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            standard_requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            log(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str}")
        
        return True

    except Exception as e:
        log(f"      ❌ Errore API WP: {e}")
        return True

def run_price_monitor():
    log("🚀 MONITORAGGIO v12.1 (FIX PREZZI + STEALTH) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            conn.close()
            
            num_prods = len(products)
            log(f"📊 Inizio scansione di {num_prods} prodotti...")

            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                
                if new_price is not None:
                    # Se il prezzo è valido, aggiorna
                    post_exists = update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal)
                    
                    if not post_exists:
                        u_conn = mysql.connector.connect(**DB_CONFIG)
                        u_curr = u_conn.cursor()
                        u_curr.execute("UPDATE products SET status = 'trash' WHERE id = %s", (p['id'],))
                        u_conn.commit()
                        u_conn.close()
                        log(f"      ✅ ASIN {p['asin']} spostato nel cestino DB.")
                    
                    elif abs(float(p['current_price']) - new_price) > 0.01:
                        u_conn = mysql.connector.connect(**DB_CONFIG)
                        u_curr = u_conn.cursor()
                        u_curr.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p['id'], new_price))
                        u_curr.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p['id']))
                        u_conn.commit()
                        u_conn.close()
                        log(f"      💰 CAMBIO RILEVATO: {p['asin']} -> € {new_price}")
                    
                    else:
                        log(f"   ⚖️  {p['asin']} Stabile (€ {p['current_price']})")
                
                else:
                    log(f"   ⚠️  Impossibile leggere prezzo per {p['asin']}")

                # PAUSA DINAMICA ANTI-BOT
                wait_time = random.uniform(20, 50)
                time.sleep(wait_time) 
            
            next_run = datetime.now() + timedelta(hours=1)
            log(f"✅ Giro completato. Pausa 1 ora. Prossimo avvio: {next_run.strftime('%H:%M:%S')}")
            time.sleep(3600)
            
        except Exception as e:
            log(f"❌ Errore critico nel loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_price_monitor()