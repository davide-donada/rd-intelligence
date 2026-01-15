import mysql.connector
import requests
import base64
import os
from datetime import datetime

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

def get_headers():
    if not WP_APP_PASSWORD: return {}
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }

def upload_image_to_wp(image_url, title):
    """Scarica l'immagine da Amazon e la carica su WordPress"""
    if not image_url: return None
    
    print(f"   📸 Scarico immagine: {title[:20]}...")
    
    try:
        # 1. Scarica immagine da Amazon
        img_resp = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        if img_resp.status_code != 200:
            print("     ⚠️ Errore download immagine.")
            return None
        
        image_data = img_resp.content
        filename = f"{title.replace(' ', '-').lower()[:50]}.jpg" # Nome file pulito

        # 2. Prepara Headers per Upload (diversi da quelli JSON)
        credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
        token = base64.b64encode(credentials.encode())
        media_headers = {
            'Authorization': f'Basic {token.decode("utf-8")}',
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'image/jpeg'
        }

        # 3. Carica su WordPress
        wp_resp = requests.post(
            f"{WP_API_URL}/media",
            headers=media_headers,
            data=image_data
        )

        if wp_resp.status_code == 201:
            media_id = wp_resp.json()['id']
            print(f"     ✅ Immagine caricata in WP (ID: {media_id})")
            return media_id
        else:
            print(f"     ❌ Errore Upload WP: {wp_resp.text}")
            return None

    except Exception as e:
        print(f"     ❌ Errore gestione immagine: {e}")
        return None

def format_article_html(product, local_image_url=None):
    asin = product[1]
    title = product[2]
    price = product[3]
    amazon_image_url = product[5]
    ai_content = product[6]

    # Usiamo l'immagine caricata se c'è, altrimenti quella di Amazon come fallback
    final_image = local_image_url if local_image_url else amazon_image_url
    
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"

    header_html = f"""
    <div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
        <div style="flex: 1; text-align: center; min-width: 200px;">
            <a href="{aff_link}" rel="nofollow sponsored" target="_blank">
                <img src="{final_image}" alt="{title}" style="max-height: 250px; width: auto; object-fit: contain;">
            </a>
        </div>
        <div style="flex: 1.5; min-width: 250px;">
            <h2 style="margin-top: 0; font-size: 1.4rem;">{title}</h2>
            <div class="rd-price-box" style="font-size: 2rem; color: #B12704; font-weight: bold; margin: 10px 0;">€ <span class="rd-price-val">{price}</span></div>
            <a href="{aff_link}" rel="nofollow sponsored" target="_blank" 
               style="background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
               👉 Vedi Offerta su Amazon
            </a>
            <p style="font-size: 0.8rem; color: #666; margin-top: 5px;">Prezzo aggiornato al: <span class="rd-date-val">{datetime.now().strftime("%d/%m/%Y")}</span></p>
        </div>
    </div>
    """

    footer_html = """
    <hr style="margin: 40px 0;">
    <p style="font-size: 0.75rem; color: #999; text-align: center;">
        RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU. Acquistando tramite i nostri link potremmo ricevere una commissione.
    </p>
    """
    return header_html + ai_content + footer_html

def run_publisher():
    print("🔌 [WP] Controllo coda pubblicazione...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Query completa
        query = "SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id FROM products WHERE status = 'draft'"
        cursor.execute(query)
        products = cursor.fetchall()
        
        if not products:
            print("💤 [WP] Nessuna bozza.")
            return

        for p in products:
            p_id = p[0]
            title = p[2]
            amazon_img = p[4]
            cat_id = p[6]
            
            print(f"   > Pubblicazione: {title[:30]}...")

            # 1. CARICAMENTO IMMAGINE REALE SU WP
            media_id = upload_image_to_wp(amazon_img, title)
            
            # Se abbiamo caricato l'immagine, recuperiamo il suo URL per usarlo nel testo
            local_img_url = None
            if media_id:
                try:
                    # Chiediamo a WP l'URL dell'immagine appena caricata
                    media_info = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers()).json()
                    local_img_url = media_info['source_url']
                except: pass

            # 2. CREAZIONE CONTENUTO
            # Ricostruiamo tupla dati per la funzione format
            product_data = [p[0], p[1], p[2], p[3], None, amazon_img, p[5]]
            
            post_content = format_article_html(product_data, local_img_url)

            # 3. PAYLOAD POST
            post_data = {
                'title': f"Recensione: {title}",
                'content': post_content,
                'status': 'draft', # Draft per sicurezza
                'categories': [cat_id],
                'featured_media': media_id if media_id else 0 # <--- IMPOSTA L'IMMAGINE IN EVIDENZA!
            }

            try:
                response = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
                if response.status_code == 201:
                    new_post_id = response.json()['id']
                    print(f"     ✅ Pubblicato ID: {new_post_id} (Img ID: {media_id})")
                    cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (new_post_id, p_id))
                    conn.commit()
                else:
                    print(f"     ❌ Errore WP: {response.text}")
            except Exception as e:
                print(f"     ❌ Errore Rete: {e}")

    except Exception as err:
        print(f"❌ DB Error: {err}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()