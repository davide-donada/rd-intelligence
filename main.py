import time
import sys
import os
import mysql.connector
import json 
from datetime import datetime

try:
    from amazon_hunter import get_amazon_data, save_to_db
    from wp_publisher import run_publisher
    from ai_writer import genera_recensione_seo
    from price_updater import update_prices_loop
    from youtube_hunter import find_video_review # <--- NUOVO IMPORT
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    sys.exit()

DB_CONFIG = {
    'user': 'root', 'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'), 'port': 3306, 'database': 'recensionedigitale'
}

# ... (Le funzioni get_next_target e mark_target_status rimangono UGUALI a prima) ...
def get_next_target():
    conn = None; target_asin = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG); cursor = conn.cursor()
        cursor.execute("SELECT asin FROM hunting_list WHERE status = 'pending' LIMIT 1")
        result = cursor.fetchone()
        if result:
            target_asin = result[0]
            cursor.execute("UPDATE hunting_list SET status = 'processing' WHERE asin = %s", (target_asin,)); conn.commit()
    except: pass
    finally:
        if conn: conn.close()
    return target_asin

def mark_target_status(asin, status):
    try:
        conn = mysql.connector.connect(**DB_CONFIG); cursor = conn.cursor()
        cursor.execute("UPDATE hunting_list SET status = %s WHERE asin = %s", (status, asin)); conn.commit(); conn.close()
    except: pass

def main_loop():
    print(f"\n--- 🤖 CICLO: {datetime.now().strftime('%H:%M:%S')} ---")
    asin = get_next_target()
    
    if not asin:
        print("💤 Coda vuota. Controllo pubblicazioni...")
        run_publisher()
        return False

    print(f"🎯 Target: {asin}")
    try:
        raw_data = get_amazon_data(asin)
        
        if raw_data and raw_data['title'] != "Titolo non trovato":
            if raw_data['price'] > 0:
                print("🧠 Generazione Contenuti (AI + Video)...")
                
                # 1. AI WRITER
                ai_result = genera_recensione_seo(raw_data)
                
                # 2. YOUTUBE HUNTER (Nuovo!) 🎥
                video_id = find_video_review(raw_data['title'])
                if video_id:
                    ai_result['video_id'] = video_id # Aggiungiamo l'ID al pacchetto JSON
                
                # 3. SALVATAGGIO
                raw_data['ai_content'] = json.dumps(ai_result) # Salviamo tutto il pacchetto
                
                raw_data['category_id'] = ai_result.get('category_id', 9)
                raw_data['meta_desc'] = ai_result.get('meta_description', '')
                
            else:
                fallback = {"html_content": "<p>Prodotto non disponibile.</p>"}
                raw_data['ai_content'] = json.dumps(fallback)
                raw_data['category_id'] = 1
                raw_data['meta_desc'] = ""

            save_to_db(raw_data)
            mark_target_status(asin, 'done')
            print(f"✅ {asin} Completato (Video: {'SI' if video_id else 'NO'}).")
        else:
            print("⚠️ Errore Scraping.")
            mark_target_status(asin, 'error')
            
    except Exception as e:
        print(f"❌ Errore Critico: {e}")
        mark_target_status(asin, 'error')

    time.sleep(10)
    return True

if __name__ == "__main__":
    print("♾️  SISTEMA ATTIVO (VIDEO EDITION 🎥)")
    cycle_count = 0
    while True:
        try: lavorato = main_loop()
        except: lavorato = False
        
        cycle_count += 1
        if cycle_count >= 10:
            print("Checking aggiornamenti prezzi...")
            try: update_prices_loop()
            except: pass
            cycle_count = 0
            
        if not lavorato: time.sleep(60)