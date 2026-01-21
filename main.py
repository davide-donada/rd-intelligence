import mysql.connector
import time
import os
import json
from datetime import datetime

# --- IMPORT MODULI ---
try:
    import amazon_hunter   
    import youtube_hunter  
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
    print("🚀 SISTEMA DI PUBBLICAZIONE RD AVVIATO...")
    
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. CERCA PRODOTTO IN CODA (Pending)
            # Abbiamo verificato che la colonna 'features' non è presente, 
            # quindi usiamo solo le colonne certe.
            query = "SELECT id, asin FROM products WHERE status = 'pending' LIMIT 1"
            cursor.execute(query)
            product = cursor.fetchone()

            if not product:
                print("💤 In attesa di nuovi ASIN nella coda...", end='\r')
                time.sleep(60)
                continue

            p_id, asin = product
            print(f"\n⚙️  ELABORAZIONE ASIN: {asin}")

            # 2. BLOCCA IL PRODOTTO (Processing)
            cursor.execute("UPDATE products SET status = 'processing' WHERE id = %s", (p_id,))
            conn.commit()

            # --- FASE 1: SCRAPING AMAZON ---
            # Recuperiamo dati puliti e immagini in HD
            product_data = amazon_hunter.get_amazon_data(asin) 

            if not product_data or not product_data.get('title'):
                print(f"   ❌ Scraping Amazon fallito per {asin}.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue
            
            # --- FASE 2: RICERCA VIDEO YOUTUBE ---
            # Cerchiamo una video recensione reale per arricchire il post
            print(f"   🎥 Ricerca video per: {product_data['title'][:40]}...")
            video_id = youtube_hunter.find_video_review(product_data['title'])
            
            # Aggiorniamo i dati base nel database
            sql_update = """
                UPDATE products 
                SET title=%s, current_price=%s, image_url=%s
                WHERE id=%s
            """
            cursor.execute(sql_update, (
                product_data.get('title'), 
                product_data.get('price', 0), 
                product_data.get('image', ''),
                p_id
            ))
            conn.commit()

            # --- FASE 3: GENERAZIONE AI (Ottica SEO) ---
            # Scrittura in terza persona plurale, senza voti nel testo
            ai_result = ai_writer.genera_recensione_seo(product_data)

            if not ai_result:
                print(f"   ❌ Errore durante la generazione del testo AI.")
                cursor.execute("UPDATE products SET status = 'failed' WHERE id = %s", (p_id,))
                conn.commit()
                continue
            
            # Integriamo il Video ID nel pacchetto dati per il publisher
            if video_id:
                ai_result['video_id'] = video_id

            # --- FASE 4: SALVATAGGIO BOZZA (Draft) ---
            cat_id = ai_result.get('category_id', 1)
            meta_desc = ai_result.get('meta_description', '')
            ai_json = json.dumps(ai_result)

            cursor.execute("""
                UPDATE products 
                SET ai_sentiment = %s, category_id = %s, meta_desc = %s, status = 'draft'
                WHERE id = %s
            """, (ai_json, cat_id, meta_desc, p_id))
            conn.commit()
            print(f"   📝 Bozza salvata con successo nel DB.")

            # --- FASE 5: PUBBLICAZIONE SU WORDPRESS ---
            # Il publisher caricherà l'immagine HD e creerà i box grafici
            print(f"   📮 Invio a WordPress in corso...")
            wp_publisher.run_publisher()
            
            print(f"   ✅ CICLO COMPLETATO: {asin}\n")
            time.sleep(10)

        except Exception as e:
            print(f"❌ ERRORE CRITICO NEL LOOP: {e}")
            time.sleep(30)
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    main_process_loop()