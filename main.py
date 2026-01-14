import time
import random
import sys
import os
import mysql.connector
from datetime import datetime

try:
    from amazon_hunter import get_amazon_data, save_to_db
    from wp_publisher import run_publisher
    from ai_writer import genera_recensione_seo
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    sys.exit()

# Configurazione DB (La stessa degli altri file)
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_next_target():
    """Pesca il prossimo ASIN 'pending' dalla lista e lo blocca"""
    conn = None
    target_asin = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 1. Troviamo il prossimo (LIMIT 1)
        cursor.execute("SELECT asin FROM hunting_list WHERE status = 'pending' LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            target_asin = result[0]
            # 2. Lo segniamo come 'processing' così nessun altro worker lo prende
            cursor.execute("UPDATE hunting_list SET status = 'processing' WHERE asin = %s", (target_asin,))
            conn.commit()
            
    except Exception as e:
        print(f"⚠️ Errore lettura coda: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return target_asin

def mark_target_status(asin, status):
    """Aggiorna lo stato nella coda (done/error)"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("UPDATE hunting_list SET status = %s WHERE asin = %s", (status, asin))
        conn.commit()
        conn.close()
    except: pass

def main_loop():
    print(f"\n--- 🤖 CICLO AVVIATO: {datetime.now().strftime('%H:%M:%S')} ---")
    
    # 1. CERCA LAVORO
    asin = get_next_target()
    
    if not asin:
        print("💤 Nessun ASIN in attesa. La coda è vuota.")
        # Se non c'è lavoro, controlliamo se c'è da pubblicare qualcosa e poi dormiamo
        print("--- ✍️ CONTROLLO PUBBLICAZIONE ---")
        run_publisher()
        return False # Ritorna False per dire "non ho lavorato"

    print(f"🎯 Trovato nuovo target: {asin}")
    
    # 2. ESECUZIONE
    try:
        raw_data = get_amazon_data(asin)
        
        if raw_data and raw_data['title'] != "Titolo non trovato":
            if raw_data['price'] > 0:
                print(f"🧠 Generazione AI in corso...")
                recensione_html = genera_recensione_seo(raw_data)
                raw_data['ai_content'] = recensione_html if recensione_html else "<p>Elaborazione...</p>"
            else:
                raw_data['ai_content'] = "<p>Prodotto non disponibile.</p>"

            save_to_db(raw_data)
            mark_target_status(asin, 'done') # ✅ Missione compiuta
            print(f"✅ {asin} completato e salvato.")
        else:
            print("⚠️ Errore scraping (Captcha o titolo vuoto).")
            mark_target_status(asin, 'error') # ❌ Segnaliamo errore
            
    except Exception as e:
        print(f"❌ Errore critico su {asin}: {e}")
        mark_target_status(asin, 'error')

    # 3. PAUSA DI SICUREZZA TRA UN ASIN E L'ALTRO
    wait = random.randint(15, 45)
    print(f"☕ Riposo {wait}s prima del prossimo...")
    time.sleep(wait)
    return True # Ho lavorato

if __name__ == "__main__":
    print("♾️  MODALITÀ INDUSTRIALE ATTIVATA")
    while True:
        ha_lavorato = main_loop()
        
        if not ha_lavorato:
            # Se la coda è vuota, dorme di più (es. 5 minuti) per non stressare il DB
            print("💤 Niente da fare. Controllo di nuovo tra 5 minuti...")
            time.sleep(300)
        # Se ha lavorato, il loop ricomincia subito (dopo la piccola pausa interna)