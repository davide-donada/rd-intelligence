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
    from price_updater import update_prices_loop # <--- Modulo nuovi prezzi
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    sys.exit()

# --- CONFIGURAZIONE DB ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_next_target():
    """Pesca il prossimo ASIN dalla coda"""
    conn = None
    target_asin = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT asin FROM hunting_list WHERE status = 'pending' LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            target_asin = result[0]
            cursor.execute("UPDATE hunting_list SET status = 'processing' WHERE asin = %s", (target_asin,))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Errore lettura coda: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
    return target_asin

def mark_target_status(asin, status):
    """Aggiorna lo stato (done/error)"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("UPDATE hunting_list SET status = %s WHERE asin = %s", (status, asin))
        conn.commit()
        conn.close()
    except: pass

def main_loop():
    """Il ciclo principale che cerca nuovi prodotti"""
    print(f"\n--- 🤖 CICLO: {datetime.now().strftime('%H:%M:%S')} ---")
    
    # 1. CERCA LAVORO
    asin = get_next_target()
    
    if not asin:
        print("💤 Coda vuota. Controllo pubblicazioni...")
        run_publisher() # Pubblica eventuali bozze in attesa
        return False # Ritorna False se non ha trovato nuovi ASIN

    print(f"🎯 Target: {asin}")
    
    # 2. ESECUZIONE
    try:
        raw_data = get_amazon_data(asin)
        
        if raw_data and raw_data['title'] != "Titolo non trovato":
            if raw_data['price'] > 0:
                print("🧠 Generazione Recensione AI...")
                html_art = genera_recensione_seo(raw_data)
                raw_data['ai_content'] = html_art if html_art else "<p>Errore generazione AI.</p>"
            else:
                raw_data['ai_content'] = "<p>Prodotto non disponibile.</p>"

            save_to_db(raw_data)
            mark_target_status(asin, 'done')
            print(f"✅ {asin} Completato e salvato.")
        else:
            print("⚠️ Errore Scraping (Captcha o titolo vuoto).")
            mark_target_status(asin, 'error')
            
    except Exception as e:
        print(f"❌ Errore Critico: {e}")
        mark_target_status(asin, 'error')

    # Piccola pausa tra un prodotto e l'altro per sicurezza
    time.sleep(10)
    return True

if __name__ == "__main__":
    print("♾️  SISTEMA ATTIVO (HUNTER + PUBLISHER + UPDATER)")
    
    cycle_count = 0
    
    while True:
        # 1. Esegue il ciclo principale (Caccia + Scrittura + Pubblicazione)
        try:
            lavorato = main_loop()
        except Exception as e:
            print(f"❌ Errore nel Main Loop: {e}")
            lavorato = False
        
        # 2. Ogni 10 cicli (circa ogni 10-20 minuti), controlla i prezzi dei vecchi articoli
        cycle_count += 1
        if cycle_count >= 10:
            print("Checking aggiornamenti prezzi...")
            try:
                update_prices_loop()
            except Exception as e:
                print(f"⚠️ Errore Updater: {e}")
            cycle_count = 0 # Reset contatore
            
        # 3. Gestione Pausa
        if not lavorato:
            # Se non c'era lavoro, dorme di più (60 secondi)
            time.sleep(60) 
        # Se ha lavorato, il loop ricomincia subito (dopo la pausa interna di 10s)