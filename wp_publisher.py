import os
import mysql.connector
import requests
import base64
from datetime import datetime

# --- CONFIGURAZIONE DATABASE ---
DB_CONFIG = {
    'user': 'root',
    # Ora legge la variabile d'ambiente, se non c'è usa 'root' come fallback (ma fallirà)
    'password': os.getenv('DB_PASSWORD', 'password_finta_per_test_locale'), 
    'host': os.getenv('DB_HOST', '80.211.135.46'), # IP Server o 'mariadb' se siamo dentro Docker
    'port': 3306,
    'database': 'recensionedigitale'
}

# --- 2. CONFIGURAZIONE WORDPRESS ---
WP_URL = "https://www.recensionedigitale.it/wp-json/wp/v2/posts"
WP_USER = "davide"                           # <--- Utente impostato
WP_APP_PASSWORD = os.getenv('WP_PASSWORD', 'xxxx xxxx xxxx')

def get_headers():
    # Creiamo l'autenticazione
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        # TRUCCO FONDAMENTALE: Mascheriamoci da browser per evitare blocchi 403/401 del server
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

def format_article_html(product):
    # Layout HTML dell'articolo
    # product = (id, asin, title, price, target, img, sentiment, json, aff_url, date, status)
    title = product[2]
    price = product[3]
    image = product[5]
    
    html = f"""
    <div style="text-align:center; margin-bottom:30px;">
        <img src="{image}" alt="{title}" style="max-width: 400px; height: auto; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
    </div>
    
    <div style="background-color: #e8f4fa; padding: 20px; border-left: 5px solid #0073aa; margin-bottom: 25px; border-radius: 4px;">
        <h3 style="margin-top: 0; color: #0073aa;">💰 Prezzo Rilevato: € {price}</h3>
        <p style="margin-bottom:0;">Rilevamento del: {datetime.now().strftime("%d/%m/%Y alle %H:%M")}</p>
    </div>

    <h2>Analisi del Prodotto</h2>
    <p>Questo articolo è stato generato automaticamente dal sistema <strong>RD-Intelligence</strong>.</p>
    <p>Stiamo aggregando le recensioni degli utenti per questo modello (ASIN: {product[1]}). A breve l'analisi completa.</p>
    <hr>
    <p><small><em>RecensioneDigitale.it - Automated Publishing System</em></small></p>
    """
    return html

def run_publisher():
    print("🔌 Connessione al Database remoto...")
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Cerchiamo prodotti con status 'draft'
        cursor.execute("SELECT * FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        if not products:
            print("💤 Nessun prodotto in 'draft' trovato. Tutto aggiornato.")
            return

        print(f"🚀 Trovati {len(products)} prodotti da pubblicare!")

        for p in products:
            p_id = p[0]
            title = p[2]
            print(f"   > Elaborazione: {title}...")

            post_data = {
                'title': f"Recensione: {title}",
                'content': format_article_html(p),
                'status': 'draft', # Lasciamo bozza per sicurezza
            }

            # Chiamata a WordPress
            try:
                response = requests.post(WP_URL, headers=get_headers(), json=post_data)

                if response.status_code == 201:
                    print("     ✅ PUBBLICATO SU WORDPRESS! (Controlla le Bozze)")
                    
                    # Aggiorna DB per non ripubblicarlo
                    cursor.execute("UPDATE products SET status = 'published' WHERE id = %s", (p_id,))
                    conn.commit()
                else:
                    print(f"     ❌ Errore WP {response.status_code}: {response.text}")
            
            except Exception as e:
                print(f"     ❌ Errore di connessione a WP: {e}")

    except mysql.connector.Error as err:
        print(f"❌ Errore Database MySQL: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("🔒 Connessione DB chiusa.")

if __name__ == "__main__":
    run_publisher()