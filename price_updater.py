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
AMAZON_TAG = "recensionedigitale-21" 

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def clean_amazon_image_url(url):
    if not url or not isinstance(url, str): return ""
    return re.sub(r'\._[A-Z0-9,_\-]+_\.', '.', url)

def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}?th=1&psc=1"
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

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label, product_title, image_url, asin):
    if not wp_post_id or wp_post_id == 0: return True
    headers = get_wp_headers()
    
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers, timeout=20)
        if resp.status_code != 200: return True
        post_data = resp.json()
        if post_data.get('status') == 'trash': return False
        content = post_data['content']['raw']
        original_content = content

        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        status_text = deal_label if deal_label else (f"📉 Ribasso di € {abs(diff):.2f}" if diff < -0.01 else (f"📈 Rialzo di € {abs(diff):.2f}" if diff > 0.01 else "⚖️ Prezzo Stabile"))
        today = datetime.now().strftime('%d/%m/%Y')
        affiliate_url = f"https://www.amazon.it/dp/{asin}?tag={AMAZON_TAG}"
        clean_img = clean_amazon_image_url(image_url)

        # --- BLOCCHI HTML DA INSERIRE ---

        styles_scripts = """
<style>
@keyframes pulse-orange { 0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0.7); } 70% { transform: scale(1.03); box-shadow: 0 0 0 10px rgba(255, 153, 0, 0); } 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0); } }
.rd-btn-pulse { animation: pulse-orange 2s infinite; }
@media (max-width: 768px) { #rd-sticky-title-id { display: none !important; } }
</style>
<script>
document.addEventListener("DOMContentLoaded", function() {
    var stickyBar = document.getElementById("rd-sticky-bar-container");
    if (stickyBar) { document.body.appendChild(stickyBar); }
    
    function checkMobile() {
        var title = document.getElementById("rd-sticky-title-id");
        if (title) {
            if (window.innerWidth < 768) { title.style.display = "none"; } 
            else { title.style.display = "block"; }
        }
    }
    window.addEventListener("resize", checkMobile);
    checkMobile();
});
</script>
"""

        new_header_block = f"""
{styles_scripts}
<div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center; position: relative;">
    <div style="flex: 1; text-align: center; min-width: 200px;">
        <a href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored">
            <img class="lazyload" style="max-height: 250px; width: auto; object-fit: contain;" src="{clean_img}" alt="Recensione {product_title}" />
        </a>
    </div>
    <div style="flex: 1.5; min-width: 250px;">
        <h2 style="margin-top: 0; font-size: 1.4rem;">{product_title}</h2>
        <div class="rd-price-box" style="font-size: 2.2rem; color: #b12704; font-weight: 800; margin: 10px 0;">€ {new_str}</div>
        <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
            <div style="font-weight: bold; color: #856404; text-transform: uppercase; font-size: 0.75rem;">Stato Attuale</div>
            <div class="rd-status-val" style="font-size: 0.9rem; color: #333; font-weight: 600;">{status_text}</div>
        </div>
        <a class="rd-btn-pulse" style="background-color: #ff9900 !important; color: #ffffff !important; padding: 14px 28px; text-decoration: none !important; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 1.1rem; margin-top: 5px;" href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored">
            👉 VEDI OFFERTA AMAZON
        </a>
        <p style="font-size: 0.75rem; color: #888; margin-top: 8px;">Ultimo controllo: {today}</p>
    </div>
</div>
"""

        new_sticky_bar = f"""
<div id="rd-sticky-bar-container" style="position: fixed !important; bottom: 0 !important; left: 0 !important; width: 100% !important; background: #ffffff !important; box-shadow: 0 -2px 10px rgba(0,0,0,0.1) !important; z-index: 2147483647 !important; border-top: 3px solid #ff9900 !important; padding: 0 !important;">
    <div style="max-width: 1100px !important; margin: 0 auto !important; padding: 10px 20px !important; display: flex !important; justify-content: space-between !important; align-items: center !important;">
        <div id="rd-sticky-title-id" style="font-weight:bold !important; color:#333 !important; max-width: 60% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; font-family: sans-serif !important; font-size: 1rem !important; margin: 0 !important;">{product_title}</div>
        <div style="display:flex !important; align-items:center !important; margin: 0 !important; margin-left: auto !important;">
            <span class="rd-sticky-price" style="font-size: 1.2rem !important; font-weight: bold !important; color: #b12704 !important; margin-right: 15px !important; white-space: nowrap !important;">€ {new_str}</span>
            <a href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored" style="background: #ff9900 !important; color: #ffffff !important; padding: 10px 20px !important; text-decoration: none !important; border-radius: 4px !important; font-weight: bold !important; text-transform: uppercase !important; font-size: 0.9rem !important; border: none !important; box-shadow: none !important; white-space: nowrap !important;">Vedi Offerta</a>
        </div>
    </div>
</div>
"""

        # --- FASE 1: PULIZIA NUCLEARE (The Nuke) ---
        
        # A. Pulizia CSS/JS (Gestisce anche <br /> intrusi)
        content = re.sub(r'<style>.*?</style>', '', content, flags=re.DOTALL)
        content = re.sub(r'<script>.*?</script>', '', content, flags=re.DOTALL)
        
        # B. Pulizia Header (Loop Aggressivo basato sulla struttura)
        # Identifica: un div che inizia con sfondo bianco, contiene immagine, prezzo e finisce con due div chiusi.
        # Mangia tutto quello che assomiglia a un box header, vecchio o nuovo.
        header_nuke_pattern = r'<div style="background-color: #fff; border: 1px solid #e1e1e1;.*?Ultimo controllo:.*?</p>\s*</div>\s*</div>'
        while re.search(header_nuke_pattern, content, re.DOTALL):
            content = re.sub(header_nuke_pattern, '', content, count=1, flags=re.DOTALL)

        # Fallback Header: cerca quelli vecchi senza stile specifico
        old_header_pattern = r'<div style="text-align: center;">.*?Prezzo aggiornato al:.*?</div>(?:\s*</div>)*'
        while re.search(old_header_pattern, content, re.DOTALL):
            content = re.sub(old_header_pattern, '', content, count=1, flags=re.DOTALL)

        # C. Pulizia Footer (South Pole Strategy)
        # Cancella TUTTO tra il Disclaimer e lo Schema.org.
        # Questo elimina sticky bar, frammenti ghost, div aperti, tutto.
        footer_nuke_pattern = r'(<p style="font-size: 0.7rem;.*?In qualità di Affiliato Amazon.*?</em></p>)(.*)(<script type="application/ld\+json">)'
        
        if re.search(footer_nuke_pattern, content, re.DOTALL):
            # Sostituisce la parte centrale (junk) con la nuova sticky bar
            content = re.sub(footer_nuke_pattern, f'\\g<1>{new_sticky_bar}\\g<3>', content, flags=re.DOTALL)
        else:
            # Se non trova il disclaimer (strano), prova a cancellare solo le sticky bar note
            sticky_loop = r'(?:\s*)?<div id="rd-sticky-bar-container".*?</div>(?:\s*)?'
            while re.search(sticky_loop, content, re.DOTALL):
                content = re.sub(sticky_loop, '', content, count=1, flags=re.DOTALL)
            
            # E appende la nuova in fondo
            if '<script type="application/ld+json">' in content:
                content = content.replace('<script type="application/ld+json">', new_sticky_bar + '\n<script type="application/ld+json">')
            else:
                content = content + new_sticky_bar

        # --- FASE 2: RICOSTRUZIONE ---
        
        # Inserisci Header (solo uno, in cima)
        content = new_header_block + content

        # --- FASE 3: METADATA ---
        content = re.sub(r'(Ultimo controllo: |Prezzo aggiornato al:\s?)(.*?)(\s*</p>|</span>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            update_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            if update_resp.status_code == 200:
                log(f"      ✨ WP NUCLEARIZZATO & RIPARATO (ID: {wp_post_id}) -> € {new_str}")
        
        return True

    except Exception as e:
        log(f"      ❌ Errore Critico WP API: {e}")
        return True

def run_price_monitor():
    log("🚀 MONITORAGGIO v17.8 (THE NUKE) AVVIATO...")
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, asin, current_price, wp_post_id, title, image_url FROM products WHERE status = 'published' ORDER BY id DESC")
            products = cursor.fetchall()
            conn.close()
            
            log(f"📊 Scansione {len(products)} prodotti...")
            
            for p in products:
                new_price, deal = get_amazon_data(p['asin'])
                
                if new_price:
                    post_exists = update_wp_post_price(p['wp_post_id'], p['current_price'], new_price, deal, p['title'], p['image_url'], p['asin'])
                    if not post_exists: pass
                    
                    if abs(float(p['current_price']) - new_price) > 0.01:
                        conn = mysql.connector.connect(**DB_CONFIG)
                        cur = conn.cursor()
                        cur.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p['id']))
                        cur.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p['id'], new_price))
                        conn.commit()
                        conn.close()
                        log(f"      💰 CAMBIO: {p['asin']} -> € {new_price}")
                    else:
                        log(f"   ⚖️  {p['asin']} Stabile")
                
                time.sleep(15)
            
            log(f"✅ Giro completato. Pausa 1 ora.")
            time.sleep(3600)
            
        except Exception as e:
            log(f"❌ Errore critico nel loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_price_monitor()