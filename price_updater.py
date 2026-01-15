import mysql.connector
import requests
import base64
import os
import re
import time
from datetime import datetime
from amazon_hunter import get_amazon_data

# --- CONFIGURAZIONE ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

WP_BASE_URL = "https://www.recensionedigitale.it/wp-json/wp/v2/posts"
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_headers():
    if not WP_APP_PASSWORD: return {}
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }

def update_prices_loop():
    print(f"\n--- 🔄 AVVIO AGGIORNAMENTO PREZZI: {datetime.now().strftime('%H:%M')} ---")
    
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 1. CERCHIAMO PRODOTTI VECCHI DI ALMENO 12 ORE (e che hanno un wp_post_id)
        # La query prende solo quelli pubblicati che hanno un ID WP valido
        query = """
        SELECT id, asin, current_price, wp_post_id, title 
        FROM products 
        WHERE status = 'published' 
        AND wp_post_id > 0
        AND last_checked < DATE_SUB(NOW(), INTERVAL 12 HOUR)
        LIMIT 5
        """
        cursor.execute(query)
        products_to_update = cursor.fetchall()
        
        if not products_to_update:
            print("💤 Nessun prezzo da aggiornare al momento.")
            return

        print(f"🎯 Trovati {len(products_to_update)} prodotti da aggiornare.")

        for p in products_to_update:
            db_id = p[0]
            asin = p[1]
            old_price = float(p[2])
            wp_id = p[3]
            title = p[4]
            
            print(f"   > Controllo: {title[:20]}... (Vecchio: {old_price}€)")

            # 2. SCARICA DATO FRESCO DA AMAZON
            new_data = get_amazon_data(asin)
            
            if not new_data or new_data['price'] == 0:
                print("     ⚠️ Errore Amazon o prodotto non disponibile. Salto.")
                continue
                
            new_price = new_data['price']
            print(f"     💰 Prezzo attuale: {new_price}€")

            # 3. AGGIORNA SU WORDPRESS (Solo se il prezzo è cambiato o sono passati giorni)
            # Scarichiamo il contenuto attuale
            try:
                wp_resp = requests.get(f"{WP_BASE_URL}/{wp_id}", headers=get_headers())
                if wp_resp.status_code != 200:
                    print(f"     ❌ Post WP {wp_id} non trovato.")
                    continue
                
                content_raw = wp_resp.json()['content']['rendered']
                
                # --- CHIRURGIA REGEX ---
                # Cerchiamo il pattern del prezzo nell'HTML e lo sostituiamo
                # Pattern cerca: € <span class="rd-price-val">123.45</span>
                # O fallback sul vecchio formato semplice
                
                # Aggiorna Prezzo
                new_content = re.sub(
                    r'€\s*<span class="rd-price-val">[0-9.,]+</span>', 
                    f'€ <span class="rd-price-val">{new_price}</span>', 
                    content_raw
                )
                
                # Fallback per vecchi articoli (senza span) - un po' più rischioso ma utile
                if new_content == content_raw:
                    new_content = re.sub(
                        r'€\s*[0-9.,]+</div>', 
                        f'€ {new_price}</div>', 
                        content_raw
                    )

                # Aggiorna Data
                today_str = datetime.now().strftime("%d/%m/%Y")
                new_content = re.sub(
                    r'Prezzo aggiornato al: <span class="rd-date-val">.*?</span>',
                    f'Prezzo aggiornato al: <span class="rd-date-val">{today_str}</span>',
                    new_content
                )
                # Fallback data vecchia
                if new_content == content_raw:
                     new_content = re.sub(
                        r'Prezzo aggiornato al: [0-9/]+',
                        f'Prezzo aggiornato al: {today_str}',
                        new_content
                    )

                # 4. SALVA SU WP
                if new_content != content_raw:
                    update_payload = {
                        'content': new_content
                    }
                    save_resp = requests.post(f"{WP_BASE_URL}/{wp_id}", headers=get_headers(), json=update_payload)
                    
                    if save_resp.status_code == 200:
                        print("     ✅ WP Aggiornato!")
                        
                        # 5. AGGIORNA DB LOCALE
                        cursor.execute("""
                            UPDATE products 
                            SET current_price = %s, last_checked = NOW() 
                            WHERE id = %s
                        """, (new_price, db_id))
                        conn.commit()
                    else:
                        print(f"     ❌ Errore salvataggio WP: {save_resp.status_code}")
                else:
                    print("     💤 Nessuna modifica HTML necessaria (Prezzo/Data identici o Regex fallita).")
                    # Aggiorniamo comunque il last_checked per non riprovare subito
                    cursor.execute("UPDATE products SET last_checked = NOW() WHERE id = %s", (db_id,))
                    conn.commit()

            except Exception as e:
                print(f"     ❌ Errore update: {e}")
                
            time.sleep(5) # Pausa tra un update e l'altro

    except Exception as err:
        print(f"❌ DB Error: {err}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    update_prices_loop()