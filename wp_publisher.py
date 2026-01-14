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

WP_URL = "https://www.recensionedigitale.it/wp-json/wp/v2/posts"
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }

def format_article_html(product):
    # product è una tupla del DB: 
    # 0:id, 1:asin, 2:title, 3:price, 4:target, 5:img, 6:ai_sentiment, ...
    
    title = product[2]
    price = product[3]
    image = product[5]
    ai_text = product[6] # <--- QUI LEGGIAMO IL TESTO DI GPT
    
    # Se l'AI non ha ancora scritto nulla, mettiamo un placeholder
    if not ai_text:
        ai_text = "<p><em>Analisi dettagliata in fase di elaborazione...</em></p>"

    html = f"""
    <div style="display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 30px; background: #fff; border: 1px solid #ddd; padding: 20px; border-radius: 8px;">
        <div style="flex: 1; min-width: 250px; text-align: center;">
            <img src="{image}" alt="{title}" style="max-width: 100%; height: auto; max-height: 300px;">
        </div>
        <div style="flex: 1; min-width: 250px; display: flex; flex-direction: column; justify-content: center;">
            <h2 style="margin-top: 0; font-size: 1.5rem; color: #333;">{title}</h2>
            <div style="font-size: 2rem; font-weight: bold; color: #B12704; margin: 10px 0;">€ {price}</div>
            <p style="color: #555; font-size: 0.9rem;">Prezzo rilevato il: {datetime.now().strftime("%d/%m/%Y")}</p>
            <a href="https://www.amazon.it/dp/{product[1]}?tag=recensionedigitale-21" target="_blank" style="display: inline-block; background-color: #FF9900; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; text-align: center;">Vedi Offerta su Amazon</a>
        </div>
    </div>

    <hr style="margin: 30px 0; border: 0; border-top: 1px solid #eee;">

    <div class="rd-review-content">
        {ai_text}
    </div>

    <hr style="margin: 30px 0;">
    
    <p style="font-size: 0.8rem; color: #888; text-align: center;">
        RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU. 
        I prezzi possono variare dopo la pubblicazione.
    </p>
    """
    return html

def run_publisher():
    print("🔌 [WP] Connessione al Database...")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Cerchiamo prodotti 'draft'
        cursor.execute("SELECT * FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        if not products:
            print("💤 [WP] Nessuna bozza da pubblicare.")
            return

        print(f"🚀 [WP] Trovati {len(products)} articoli da creare!")

        for p in products:
            title = p[2]
            print(f"   > Pubblicazione: {title[:30]}...")

            post_data = {
                'title': f"Recensione: {title}",
                'content': format_article_html(p),
                'status': 'draft', # O 'publish' se ti fidi ciecamente
                # 'categories': [1] # ID categoria News/Recensioni
            }

            try:
                response = requests.post(WP_URL, headers=get_headers(), json=post_data)
                if response.status_code == 201:
                    print("     ✅ Successo!")
                    # Aggiorna lo stato nel DB
                    cursor.execute("UPDATE products SET status = 'published' WHERE id = %s", (p[0],))
                    conn.commit()
                else:
                    print(f"     ❌ Errore WP {response.status_code}: {response.text}")
            except Exception as e:
                print(f"     ❌ Errore Network: {e}")

    except mysql.connector.Error as err:
        print(f"❌ Errore DB: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()