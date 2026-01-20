import mysql.connector
import time
import os
import json
from datetime import datetime

# --- IMPORT MODULI ---
try:
    import amazon_hunter   # Scraper Amazon
    import youtube_hunter  # Scraper YouTube
    import ai_writer       # Scrittore AI
    import wp_publisher    # Pubblicatore WordPress
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    print("Verifica che i file: amazon_hunter.py, youtube_hunter.py, ai_writer.py, wp_publisher.py siano presenti.")
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
    print("🚀 SISTEMA (Full + YouTube) AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. PRENDIAMO UN PRODOTTO IN CODA
            # Usiamo solo colonne sicure
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

            # --- FASE 1: SCRAPING AMAZON ---
            #
            product_data = amazon_hunter.get_amazon_data(asin) 

            # Controllo fallimento scraping
            if not product_data or not product_data.get('title') or product_data.get('title') == "Titolo non trovato":
                print(f"   ❌ Scraping Amazon fallito.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue
            
            # --- FASE 1.5: CACCIA SU YOUTUBE (Il pezzo mancante) ---
            #
            print(f"   🎥 Cerco video per: {product_data['title'][:30]}...")
            video_id = youtube_hunter.find_video_review(product_data['title'])
            
            # AGGIORNAMENTO DATI BASE NEL DB
            # Nota: Salviamo solo i dati essenziali per non rompere il DB
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
            #
            ai_result = ai_writer.genera_recensione_seo(product_data)

            if not ai_result or ai_result.get('html_content') == "<p>Errore.</p>":
                print(f"   ❌ Errore AI.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue
            
            # --- INIEZIONE VIDEO ID ---
            # Inseriamo il video trovato dentro il pacchetto dati dell'AI
            # Così wp_publisher lo troverà quando leggerà il JSON
            if video_id:
                ai_result['video_id'] = video_id
                print(f"   ✅ Video integrato nel pacchetto dati.")

            # Salvataggio AI (JSON completo con Video ID dentro)
            cat_id = ai_result.get('category_id', 9)
            meta_desc = ai_result.get('meta_description', '')
            ai_json = json.dumps(ai_result)

            cursor.execute("""
                UPDATE products 
                SET ai_sentiment = %s, category_id = %s, meta_desc = %s, status = 'draft'
                WHERE id = %s
            """, (ai_json, cat_id, meta_desc, p_id))
            conn.commit()
            print(f"   📝 Bozza salvata (con Video).")

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