import mysql.connector
import time
import os
import json
from datetime import datetime

# --- IMPORT MODULI ---
try:
    import amazon_hunter   
    import ai_writer       
    import wp_publisher    
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    exit()

# --- CONFIGURAZIONE DB ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def main_process_loop():
    print("🚀 SISTEMA (Stable) AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. PRENDIAMO UN PRODOTTO IN CODA
            query = "SELECT id, asin FROM products WHERE status = 'pending' LIMIT 1"
            cursor.execute(query)
            product = cursor.fetchone()

            if not product:
                print("💤 Coda vuota...", end='\r')
                time.sleep(60)
                continue

            p_id, asin = product
            print(f"\n⚙️  LAVORO SU: {asin}...")

            # 2. SETTIAMO IN PROCESSING
            cursor.execute("UPDATE products SET status = 'processing' WHERE id = %s", (p_id,))
            conn.commit()

            # --- FASE 1: SCRAPING ---
            product_data = amazon_hunter.get_amazon_data(asin) 

            # Controllo fallimento scraping
            if not product_data or not product_data.get('title') or product_data.get('title') == "Titolo non trovato":
                print(f"   ❌ Scraping fallito.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue

            # AGGIORNAMENTO DATI BASE (Solo colonne sicure)
            sql_update = """
                UPDATE products 
                SET title=%s, current_price=%s, image_url=%s
                WHERE id=%s
            """
            vals = (
                product_data.get('title'), 
                product_data.get('price', 0), 
                product_data.get('image', ''),
                p_id
            )
            cursor.execute(sql_update, vals)
            conn.commit()

            # --- FASE 2: AI ---
            ai_result = ai_writer.genera_recensione_seo(product_data)

            if not ai_result or ai_result.get('html_content') == "<p>Errore.</p>":
                print(f"   ❌ Errore AI.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue

            # Salvataggio AI
            cat_id = ai_result.get('category_id', 9)
            meta_desc = ai_result.get('meta_description', '')
            ai_json = json.dumps(ai_result)

            cursor.execute("""
                UPDATE products 
                SET ai_sentiment = %s, category_id = %s, meta_desc = %s, status = 'draft'
                WHERE id = %s
            """, (ai_json, cat_id, meta_desc, p_id))
            conn.commit()
            print(f"   📝 Bozza salvata.")

            # --- FASE 3: PUBBLICAZIONE ---
            print(f"   📮 Pubblicazione...")
            wp_publisher.run_publisher()
            
            print(f"   ✅ COMPLETATO: {asin}.\n")
            time.sleep(5)

        except Exception as e:
            print(f"❌ CRITICAL ERROR: {e}")
            time.sleep(30)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    main_process_loop()