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
    """Restituisce (prezzo_float, tipo_offerta_stringa) con logica di precisione"""
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        soup = BeautifulSoup(resp.content, "lxml")
        
        # 1. SCRAPING PREZZO
        price_el = soup.select_one('span.a-price span.a-offscreen')
        price_val = float(price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()) if price_el else None
        
        # 2. RILEVAMENTO OFFERTE DI PRECISIONE
        deal_type = None
        
        # Cerchiamo i badge specifici sopra o vicino al prezzo
        # Il contenitore principale delle offerte su Amazon è spesso '#apex_desktop' o '.a-section.a-spacing-none.a-spacing-top-mini'
        badge_section = soup.select_one('#apex_desktop') or soup
        badge_text = ""
        
        # Cerchiamo tag specifici per i badge (Offerta a tempo, Black Friday, Prime Day)
        badge_el = badge_section.select_one('.a-badge-label-container, .badge-region, #dealBadge_feature_div')
        if badge_el:
            badge_text = badge_el.get_text().lower()

        # Controlliamo anche la sezione sconti (Risparmi)
        savings_section = badge_section.select_one('.priceBlockSavingsString, .a-span12.a-color-price.a-size-base')
        savings_text = savings_section.get_text().lower() if savings_section else ""

        # PRIORITÀ 1: Offerta a Tempo (Lightning Deal)
        if "tempo" in badge_text or "tempo" in savings_text:
            deal_type = "⚡ Offerta a Tempo"
        
        # PRIORITÀ 2: Eventi Speciali (Black Friday / Prime Day)
        elif "black friday" in badge_text:
            deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text:
            deal_type = "🔵 Offerta Prime Day"
        elif "festa delle offerte" in badge_text:
            deal_type = "🎉 Festa delle Offerte"
            
        # PRIORITÀ 3: Ribasso generico (solo se c'è un badge ma non è un evento)
        elif badge_text.strip() != "":
            deal_type = "🏷️ Prezzo Scontato"
        
        return price_val, deal_type
    except: 
        return None, None

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

        label_html = f'''\n<div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
<div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
<div class="rd-status-val" style="font-size: 0.8rem; color: #555;">{status_text}</div>
</div>'''

        # Update Prezzo
        price_pattern = r'(<(p|div)[^>]*(?:color:\s?#b12704|rd-price-box)[^>]*>)(.*?)(</\2>)'
        content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>', content, flags=re.IGNORECASE)

        # Update Etichetta (Precisione Classe)
        class_pattern = r'(class="rd-status-val"[^>]*>)(.*?)(</div>)'
        header_fix_pattern = r'(uppercase; font-size: 0.85rem;">)(.*?)(</div>)'
        old_label_pattern = r'(<(small|div)[^>]*>)(Analisi in corso\.\.\.|Monitoraggio.*?|⚖️.*?|📉.*?|📈.*?|⚡.*?|🖤.*?|🏷️.*?|Stato Offerta.*?)(</\2>)'

        if 'class="rd-status-val"' in content:
            content = re.sub(class_pattern, f'\\g<1>{status_text}\\g<3>', content, flags=re.IGNORECASE)
        elif "Stato Offerta" in content or "uppercase" in content:
            content = re.sub(header_fix_pattern, f'\\g<1>Stato Offerta\\g<3>', content, count=1, flags=re.IGNORECASE)
            content = re.sub(old_label_pattern, f'\\g<1>{status_text}\\g<4>', content, count=1, flags=re.IGNORECASE)
        else:
            content = re.sub(price_pattern, f'\\g<1>€ {new_str}\\g<4>{label_html}', content, flags=re.IGNORECASE)

        # Update Data e JSON
        today = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'(Prezzo aggiornato al:.*?>)(.*?)(</span>|</p>)', f'\\g<1>{today}\\g<3>', content, flags=re.IGNORECASE)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\g<1>{new_str}\\g<3>', content)

        if content != original_content: 
            requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            print(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str} | {status_text}")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO v11 (PRECISION) AVVIATO...")
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