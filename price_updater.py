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
    """
    Restituisce una tupla: (prezzo_float, tipo_offerta_stringa)
    """
    url = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return None, None
        
        soup = BeautifulSoup(resp.content, "lxml")
        
        # 1. PREZZO
        price_val = None
        price_el = soup.select_one('span.a-price span.a-offscreen')
        if price_el:
            price_str = price_el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
            price_val = float(price_str)
            
        # 2. TIPO OFFERTA (Deal detection)
        deal_type = None
        text_content = soup.get_text().lower()
        
        # Cerchiamo badge specifici nel DOM o parole chiave
        # Priorità alta: Black Friday / Prime Day
        if "black friday" in text_content and "offerta" in text_content:
            deal_type = "🖤 OFFERTA BLACK FRIDAY"
        elif "prime day" in text_content:
            deal_type = "🔵 OFFERTA PRIME DAY"
        elif "festa delle offerte" in text_content:
            deal_type = "🎉 FESTA DELLE OFFERTE"
            
        # Priorità media: Offerte a tempo / Lampo
        elif soup.select_one('.a-badge-label') or "offerta a tempo" in text_content:
            deal_type = "⚡ OFFERTA A TEMPO"
        elif "offerta limitata" in text_content:
            deal_type = "⏳ OFFERTA LIMITATA"
            
        # Priorità bassa: Generico
        elif "risparmi:" in text_content or "consigliata:" in text_content:
            # Se c'è scritto "Risparmi:", è un'offerta generica
            deal_type = "🏷️ PREZZO SCONTATO"

        return price_val, deal_type

    except Exception as e:
        print(f"   ⚠️ Errore scraping ASIN {asin}: {e}")
        return None, None

def update_wp_post_price(wp_post_id, old_price, new_price, deal_label):
    if not wp_post_id or wp_post_id == 0: return
    
    headers = get_wp_headers()
    try:
        # 1. Recupera il post
        resp = requests.get(f"{WP_API_URL}/posts/{wp_post_id}?context=edit", headers=headers)
        if resp.status_code != 200: return
        
        post_data = resp.json()
        content = post_data['content']['raw']
        original_content = content
        
        new_str_dot = f"{new_price:.2f}"
        
        # --- LOGICA ETICHETTA ---
        # Se Amazon ci ha dato un'etichetta speciale (es. Black Friday), usiamo quella.
        # Altrimenti calcoliamo la differenza matematica.
        
        final_label = ""
        
        if deal_label:
            # C'è un evento Amazon attivo!
            final_label = deal_label
        else:
            # Nessun evento, usiamo la matematica
            diff = new_price - float(old_price)
            if diff < -0.01: # Sconto
                final_label = f"📉 Ribasso di € {abs(diff):.2f}"
            elif diff > 0.01: # Aumento
                final_label = f"📈 Rialzo di € {abs(diff):.2f}"
            else:
                final_label = "⚖️ Prezzo Stabile"

        # HTML Prezzo Pulito
        clean_price_html = f"<p style='font-size:1.8rem; color:#B12704; margin-bottom:5px;'><strong>€ {new_str_dot}</strong></p>"

        # --- AGGIORNAMENTO PREZZO (Metodo Safe) ---
        pattern_std = r"(<p[^>]*color:\s?#B12704[^>]*>\s*<strong>\s*€\s?)([\d\.,]+)(\s*</strong>\s*</p>)"
        pattern_fix = r"(<p[^>]*color:\s?#B12704[^>]*>\s*<strong>)(.*?)(</strong>\s*</p>)"
        pattern_reconstruct = r"(</h2>\s*)([\s\S]*?)(\s*<div style=\"border-left)"

        if re.search(pattern_std, content, re.IGNORECASE):
            content = re.sub(pattern_std, f"\\g<1>{new_str_dot}\\g<3>", content, flags=re.IGNORECASE)
        elif re.search(pattern_fix, content, re.IGNORECASE):
            content = re.sub(pattern_fix, f"\\g<1>€ {new_str_dot}\\g<3>", content, flags=re.IGNORECASE)
        elif re.search(pattern_reconstruct, content, re.IGNORECASE):
            content = re.sub(pattern_reconstruct, f"\\g<1>\n{clean_price_html}\n\\g<3>", content, flags=re.IGNORECASE)

        # --- AGGIORNAMENTO ETICHETTA WIDGET ---
        # Cerca: <small>....</small>
        # Sostituisce con la nuova etichetta
        
        # Regex più aggressiva per prendere tutto il contenuto dello small
        label_pattern = r"(<small>)(.*?)(</small>)"
        
        # Cerchiamo solo la prima occorrenza dopo il titolo o vicino al widget per sicurezza
        # Ma dato che il template è standard, sostituiamo il primo <small> che contiene testo tipico
        
        # Lista di possibili testi vecchi per ancorare la ricerca
        triggers = "Monitoraggio|Variazione|Ribasso|Rialzo|OFFERTA|PREZZO|Stabile"
        specific_label_pattern = f"(<small>)({triggers}.*?)(</small>)"
        
        if re.search(specific_label_pattern, content, re.IGNORECASE):
            print(f"      🏷️ Nuova Etichetta: {final_label}")
            content = re.sub(specific_label_pattern, f"\\g<1>{final_label}\\g<3>", content, count=1, flags=re.IGNORECASE)
        else:
            # Fallback: Se non trova i testi noti, prova a cercare uno small vicino al div del prezzo
            # Questo è rischioso ma necessario se il testo è corrotto.
            pass

        # --- FIX SCHEMA JSON ---
        json_pattern = r'("offers":\s*\{"@type":\s*"Offer",\s*)(.*?)(,\s*"priceCurrency")'
        content = re.sub(json_pattern, f'\\g<1>"price": "{new_str_dot}"\\g<3>', content)
        
        old_json_pattern = r'("price":\s?")([\d\.]+)(",)'
        if re.search(old_json_pattern, content):
            content = re.sub(old_json_pattern, f'\\g<1>{new_str_dot}\\g<3>', content)

        # Aggiornamento Data
        today_str = datetime.now().strftime('%d/%m/%Y')
        content = re.sub(r'Prezzo aggiornato al: \d{2}/\d{2}/\d{4}', f'Prezzo aggiornato al: {today_str}', content)

        # 2. INVIO DATI
        if content != original_content: 
            update_data = {'content': content}
            up_resp = requests.post(f"{WP_API_URL}/posts/{wp_post_id}", headers=headers, json=update_data)
            
            if up_resp.status_code == 200:
                print(f"      ✨ WordPress Aggiornato (ID: {wp_post_id}) -> € {new_str_dot}")
            else:
                print(f"      ❌ Errore API: {up_resp.text}")
        else:
            print("      ⚠️ Nessuna modifica necessaria.")

    except Exception as e:
        print(f"      ❌ Errore critico: {e}")

def run_price_monitor():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] MONITORAGGIO (V.8 DEAL HUNTER) AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id, asin, current_price, wp_post_id FROM products WHERE status = 'published'")
            products = cursor.fetchall()
            
            print(f"📊 Scansione di {len(products)} prodotti...")
            
            for p_id, asin, old_price, wp_id in products:
                # Ora otteniamo sia il prezzo che il tipo di offerta
                new_price, deal_type = get_amazon_data(asin)
                
                # Aggiorniamo SE:
                # 1. Il prezzo cambia (> 0.01)
                # 2. OPPURE se rileviamo un'offerta speciale (anche se il prezzo numerico non è cambiato dall'ultima scansione, magari l'etichetta è nuova)
                # Per semplicità ed evitare spam di update, aggiorniamo se c'è cambio prezzo o se l'etichetta è "forte".
                
                should_update = False
                if new_price and abs(float(old_price) - new_price) > 0.01:
                    should_update = True
                    print(f"   💰 {asin}: CAMBIATO! €{old_price} -> €{new_price}")
                elif new_price and deal_type:
                    # Opzionale: Se vuoi aggiornare l'etichetta anche a prezzo invariato (es. inizia il Black Friday)
                    # Scommenta sotto per forzare update. Per ora lasciamo legato al prezzo per non sovraccaricare.
                    # should_update = True 
                    pass

                if should_update:
                    cursor.execute("UPDATE products SET current_price = %s WHERE id = %s", (new_price, p_id))
                    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, new_price))
                    conn.commit()
                    
                    update_wp_post_price(wp_id, old_price, new_price, deal_type)
                else:
                    status_msg = f"Stabile (€{old_price})"
                    if deal_type: status_msg += f" [{deal_type}]"
                    print(f"   ⚖️ {asin}: {status_msg}")
                
                time.sleep(15) # Rispetto per Amazon
                
            print(f"✅ Giro completato. Pausa 1 ora.")
            time.sleep(3600)
            
        except Exception as e:
            print(f"❌ Errore monitor: {e}")
            time.sleep(60)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_price_monitor()