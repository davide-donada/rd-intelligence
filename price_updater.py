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
    """Restituisce (prezzo_float, tipo_offerta_stringa)"""
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        soup = BeautifulSoup(resp.content, "lxml")
        
        # 1. Scraping Prezzo
        price_val = None
        price_el = soup.select_one('span.a-price span.a-offscreen')
        if price_el:
            price_str = price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
            price_val = float(price_str)
            
        # 2. Scraping Offerte
        deal_type = None
        text_content = soup.get_text().lower()
        if "black friday" in text_content: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in text_content: deal_type = "🔵 Offerta Prime Day"
        elif "offerta a tempo" in text_content or soup.select_one('.a-badge-label'): 
            deal_type = "⚡ Offerta a Tempo"
        elif "festa delle offerte" in text_content: deal_type = "🎉 Festa delle Offerte"
        
        return price_val, deal_type
    except:
        return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return
    headers = get_wp_headers()
    try:
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        if resp.status_code != 200: return
        
        post_data = resp.json()
        content = post_data['content']['raw']
        original_content = content
        
        new_str = f"{new_price:.2f}"
        diff = new_price - float(old_price)
        
        # Determinazione Etichetta Dinamica
        if deal_label:
            status_text = deal_label
        elif diff < -0.01:
            status_text = f"📉 Ribasso di € {abs(diff):.2f}"
        elif diff > 0.01:
            status_text = f"📈 Rialzo di € {abs(diff):.2f}"
        else:
            status_text = "⚖️ Prezzo Stabile"

        # --- 1. AGGIORNAMENTO PREZZO (Metodo Universale P/DIV + Fix Corruzione) ---
        price_pattern = r'(<(p|div)[^>]*color:\s?#b12704[^>]*>)(.*?)(</\2>)'
        
        if re.search(price_pattern, content, re.IGNORECASE):
            content = re.sub(price_pattern, f'\\g<1>€ {new_s}\\g<4>', content, flags=re.IGNORECASE)
        else:
            # Ricostruzione se sparito
            reconstruct_pattern = r"(</h2>\s*)([\s\S]*?)(\s*<div style=\"(?:border-left|background-color: #fff; border: 1px solid #e1e1e1))"
            if re.search(reconstruct_pattern, content, re.IGNORECASE):
                new_box = f"\n<p style='font-size:1.8rem; color:#B12704; margin-bottom:5px;'><strong>€ {new_str}</strong></p>\n"
                content = re.sub(reconstruct_pattern, f"\\g<1>{new_box}\\g<3>", content, flags=re.IGNORECASE)

        # --- 2. AGGIORNAMENTO ETICHETTA (Supporta SMALL e DIV di stato) ---
        label_pattern = r'(<(small|div)[^>]*>)(Analisi in corso\.\.\.|Monitoraggio.*?|⚖️.*?|📉.*?|📈.*?|⚡.*?|🖤.*?|🏷️.*?)(</\2>)'
        content = re.sub(label_pattern, f'\\g<1>{status_text}\\g<4>', content, count=2, flags=re.IGNORECASE)

        # --- 3. AGGIORNAMENTO DATA ---
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # --- 4. FIX SCHEMA JSON ---
        json_fix_pattern = r'("offers":\s*\{"@type":\s*"Offer",\s*)(.*?)(,\s*"priceCurrency")'
        content = re.sub(json_fix_pattern, f'\\g<1>"price": "{new_str}"\\g<3>', content)
        content = re.sub(r'("price":\s?")([\d\.]+)(",)', f'\\1{new_str}\\3', content)

        # --- 5. INVIO AL SERVER ---
        if content != original_content: 
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json={'content': content})
            if up_resp.status_code == 200:
                print(f"      ✨ WP Aggiornato (ID: {wp_post_id}) -> € {new_str} | {status_text}")
            else:
                print(f"      ❌ Errore API WP: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica necessaria.")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO v10 (EVENT TRIGGER) AVVIATO...")
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            
            print(f"📊 Scansione di {len(products)} prodotti...")
            
            for p_id, asin, old_price, wp_id in products:
                new_price, deal = get_amazon_data(asin)
                
                # --- LOGICA DI ATTIVAZIONE AGGIORNATA ---
                price_changed = new_price and abs(float(old_price) - new_price) > 0.01
                event_detected = deal is not None # Se c'è un badge speciale (Black Friday, ecc)
                
                if price_changed or event_detected:
                    if price_changed:
                        print(f"   💰 {asin}: CAMBIATO! €{old_price} -> €{new_price} {'['+deal+']' if deal else ''}")
                        # Aggiorniamo Database solo se il prezzo è effettivamente cambiato
                        cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                        cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                        conn.commit()
                    else:
                        print(f"   🔥 {asin}: PREZZO STABILE MA EVENTO RILEVATO: [{deal}]")
                    
                    # Aggiorniamo SEMPRE WordPress se il prezzo è cambiato O se c'è un evento
                    # Passiamo il new_price se disponibile, altrimenti l'old_price
                    final_price_to_send = new_price if new_price else float(old_price)
                    update_wp_post_price(wp_id, old_price, final_price_to_send, deal)
                
                else:
                    print(f"   ⚖️ {asin}: Stabile (€{old_price}) - Nessun evento.")
                
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