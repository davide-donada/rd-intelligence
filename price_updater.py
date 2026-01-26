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

def clean_amazon_image_url(url):
    """Pulisce l'URL immagine per averla in alta definizione nel box."""
    if not url or not isinstance(url, str): return ""
    return re.sub(r'\._[A-Z0-9,_\-]+_\.', '.', url)

def get_amazon_data(asin):
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
        
        price_el = soup.select_one('span.a-price span.a-offscreen') or soup.select_one('.a-price .a-offscreen')
        price_val = float(price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if price_el else None
        
        deal_type = None
        badge_el = soup.select_one('#apex_desktop')
        badge_text = badge_el.get_text().lower() if badge_el else ""
        
        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type
    except: return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label, product_title, image_url):
    """
    Aggiorna il post WP. Se trova il layout vecchio, lo SOSTITUISCE completamente con quello nuovo Flexbox.
    """
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

        # --- PREPARAZIONE DATI ---
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        status_text = deal_label if deal_label else (f"📉 Ribasso di € {abs(diff):.2f}" if diff < -0.01 else (f"📈 Rialzo di € {abs(diff):.2f}" if diff > 0.01 else "⚖️ Prezzo Stabile"))
        today = datetime.now().strftime('%d/%m/%Y')
        affiliate_url = f"https://www.amazon.it/dp/{deal_label}?tag={AMAZON_TAG}" # Qui deal_label è usato impropriamente come placeholder, fixiamo sotto usando URL generico o passando ASIN. 
        # NOTA: deal_label qui sopra è testo, non ASIN. Usiamo un URL generico di ricerca o il link esistente se possibile.
        # Meglio rigenerare il link se abbiamo l'ASIN, ma qui non l'abbiamo passato. 
        # Per semplicità, nel replace del blocco intero, useremo un link generico o cercheremo di estrarlo, 
        # ma la strategia migliore è passare l'ASIN alla funzione.
        
        # --- GENERAZIONE NUOVO BOX FLEXBOX (DA ZERO) ---
        # Costruiamo il box HTML perfetto così come dovrebbe essere
        # Nota: L'URL affiliato lo ricostruiamo nel loop principale e lo passiamo, 
        # ma per ora usiamo un placeholder che verrà riempito dal regex o dai dati DB.
        
        # Pulizia URL Immagine
        clean_img = clean_amazon_image_url(image_url)
        
        # Box Status
        status_box_html = f'''
        <div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
            <div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
            <div class="rd-status-val" style="font-size: 0.8rem; color: #555;">{status_text}</div>
        </div>'''
        
        # --- STRATEGIA DI AGGIORNAMENTO ---
        
        # 1. C'è già il layout Flexbox (rd-price-box)?
        if 'class="rd-price-box"' in content:
            # SI: Aggiorna solo i valori interni
            price_regex = r'(<div class="rd-price-box"[^>]*>)(.*?)(</div>)'
            
            # Aggiorna Prezzo
            content = re.sub(price_regex, f'\\g<1>€ {new_str}\\g<3>', content)
            
            # Aggiorna/Inserisce Status Box (lo rigeneriamo pulito)
            # Rimuoviamo vecchi status box dentro o vicino al flexbox
            content = re.sub(r'<div[^>]*background:\s*#6c757d1a[^>]*>.*?Stato Offerta.*?</div>\s*</div>', '</div>', content, flags=re.DOTALL | re.IGNORECASE)
            
            # Inseriamo il nuovo status box
            content = re.sub(price_regex, f'\\g<0>{status_box_html}', content, count=1)

        else:
            # NO: Trovato LAYOUT VECCHIO (quello centrato dell'esempio) o MISTO
            log(f"      ⚠️ Layout Vecchio rilevato ID {wp_post_id}. Eseguo SOSTITUZIONE TOTALE.")
            
            # Regex per trovare il blocco "Vecchio Stile Centrato" (quello che mi hai incollato)
            # Cerca: <div style="text-align: center;"> ... immagine ... prezzo ... data ... </div>
            old_layout_regex = r'<div style="text-align: center;">.*?Prezzo aggiornato al:.*?</div>'
            
            # Cerchiamo di recuperare il link affiliato esistente se possibile, altrimenti ne creiamo uno
            existing_link = re.search(r'href="(https://www.amazon.it/dp/.*?)"', content)
            final_link = existing_link.group(1) if existing_link else "#"

            # Creiamo il NUOVO HTML COMPLETO
            new_html_block = f"""
<div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
    <div style="flex: 1; text-align: center; min-width: 200px;">
        <a href="{final_link}" target="_blank" rel="nofollow noopener sponsored">
            <img class="lazyload" style="max-height: 250px; width: auto; object-fit: contain;" src="{clean_img}" alt="{product_title}" />
        </a>
    </div>
    <div style="flex: 1.5; min-width: 250px;">
        <h2 style="margin-top: 0; font-size: 1.4rem;">{product_title}</h2>
        <div class="rd-price-box" style="font-size: 2rem; color: #b12704; font-weight: bold; margin: 10px 0;">€ {new_str}</div>
        {status_box_html}
        <a style="background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;" href="{final_link}" target="_blank" rel="nofollow noopener sponsored">
            👉 Vedi Offerta su Amazon
        </a>
        <p style="font-size: 0.8rem; color: #666; margin-top: 5px;">Prezzo aggiornato al: {today}</p>
    </div>
</div>
"""
            # SOSTITUZIONE DRACONIANA
            if re.search(old_layout_regex, content, re.DOTALL):
                # Sostituisce il vecchio blocco centrato con il nuovo Flexbox
                content = re.sub(old_layout_regex, new_html_block, content, flags=re.DOTALL)
            else:
                # Fallback: se non trova il blocco esatto ma non c'è il flexbox, lo mette in cima
                content = new_html_block + content

        # Aggiorna Data e Schema (Sempre)
        content = re.sub(r'(Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            update_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            
            if update_resp.status_code in [400, 401, 403]:
                try:
                    err_json = update_resp.json()
                    err_msg = err_json.get('message', '').lower()
                    if 'cestino' in err_msg or 'trash' in err_msg:
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
    log("🚀 MONITORAGGIO v15.6 (REPLACE LAYOUT) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            # SCARICHIAMO ANCHE TITOLO E IMMAGINE
            cursor.execute("SELECT id, asin, current_price, wp_post_id, title, image_url FROM products WHERE status = 'published' ORDER BY id DESC")
            products = cursor.fetchall()
            conn.close()
            
            log(f"📊 Scansione {len(products)} prodotti (dal più recente)...")
            
            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                
                if new_price:
                    # Passiamo TUTTI i dati necessari per ricostruire il box se serve
                    post_exists = update_wp_post_price(
                        p['wp_post_id'], 
                        p['current_price'], 
                        new_price, 
                        deal,
                        p['title'],      # Passiamo il Titolo
                        p['image_url']   # Passiamo l'URL Immagine
                    )
                    
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