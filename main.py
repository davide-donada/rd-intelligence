import mysql.connector
import time
import os
import json
import random
from datetime import datetime

# --- IMPORT MODULI CORRETTI ---
try:
    import amazon_hunter   # FILE SCRAPER
    import ai_writer       # FILE AI
    import wp_publisher    # FILE PUBBLICAZIONE
except ImportError as e:
    print(f"❌ ERRORE IMPORT: Non trovo un file. {e}")
    print("Verifica che i file si chiamino: amazon_hunter.py, ai_writer.py, wp_publisher.py")
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
    print("🚀 SISTEMA AVVIATO: In attesa di prodotti in 'pending'...")
    
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. CERCA PRODOTTO PENDING
            query = "SELECT id, asin FROM products WHERE status = 'pending' LIMIT 1"
            cursor.execute(query)
            product = cursor.fetchone()

            if not product:
                # Coda vuota
                print("💤 Coda vuota. Attendo...", end='\r')
                time.sleep(60)
                continue

            p_id, asin = product
            print(f"\n⚙️  TROVATO ASIN: {asin}. Inizio lavorazione...")

            # 2. BLOCCA IL PRODOTTO
            cursor.execute("UPDATE products SET status = 'processing', last_update = NOW() WHERE id = %s", (p_id,))
            conn.commit()

            # --- FASE 1: SCRAPING AMAZON (amazon_hunter) ---
            # La funzione nel tuo file si chiama get_amazon_data
            product_data = amazon_hunter.get_amazon_data(asin) 

            if not product_data or not product_data.get('title') or product_data.get('title') == "Titolo non trovato":
                print(f"   ❌ Scraping fallito per {asin}.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue

            # Aggiorniamo i dati grezzi nel DB
            # Nota: amazon_hunter ritorna 'image', ma noi salviamo in 'image_url'
            # Nota: amazon_hunter non ritorna rating/reviews, mettiamo default 0
            sql_update = """
                UPDATE products 
                SET title=%s, current_price=%s, description=%s, features=%s, 
                    image_url=%s, review_count=%s, rating=%s, last_update=NOW()
                WHERE id=%s
            """
            vals = (
                product_data.get('title'), 
                product_data.get('price', 0), 
                product_data.get('features', ''), # Uso features anche come descrizione base
                product_data.get('features', ''),
                product_data.get('image', ''),    # Mappatura corretta chiave 'image'
                0,    # Review count default
                0.0,  # Rating default
                p_id
            )
            cursor.execute(sql_update, vals)
            conn.commit()

            # --- FASE 2: INTELLIGENZA ARTIFICIALE (ai_writer) ---
            # La funzione nel tuo file si chiama genera_recensione_seo
            ai_result = ai_writer.genera_recensione_seo(product_data)

            if not ai_result or ai_result.get('html_content') == "<p>Errore.</p>":
                print(f"   ❌ Errore AI per {asin}.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue

            # Salviamo il risultato AI
            cat_id = ai_result.get('category_id', 9)
            meta_desc = ai_result.get('meta_description', '')
            ai_json = json.dumps(ai_result)

            cursor.execute("""
                UPDATE products 
                SET ai_sentiment = %s, category_id = %s, meta_desc = %s, status = 'draft', last_update = NOW()
                WHERE id = %s
            """, (ai_json, cat_id, meta_desc, p_id))
            conn.commit()
            print(f"   📝 Bozza salvata nel Database.")

            # --- FASE 3: PUBBLICAZIONE WORDPRESS (wp_publisher) ---
            # wp_publisher.run_publisher() cerca prodotti in 'draft' e li pubblica
            print(f"   📮 Avvio Pubblicazione WP...")
            wp_publisher.run_publisher()
            
            print(f"   ✅ CICLO COMPLETATO per {asin}.\n")
            
            time.sleep(10)

        except Exception as e:
            print(f"❌ CRITICAL ERROR nel Main Loop: {e}")
            time.sleep(30)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    main_process_loop()