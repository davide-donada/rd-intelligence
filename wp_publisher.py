import mysql.connector
import requests
import base64
import os
from datetime import datetime

# --- CONFIGURAZIONE DATABASE ---
# Legge le credenziali dalle variabili d'ambiente di Coolify
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

# --- CONFIGURAZIONE WORDPRESS ---
WP_URL = "https://www.recensionedigitale.it/wp-json/wp/v2/posts"
# Se non trova WP_USER nelle variabili, usa 'davide' come default
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_headers():
    """Genera gli header per l'autenticazione WordPress"""
    if not WP_APP_PASSWORD:
        print("❌ ERRORE: Manca la WP_PASSWORD nelle variabili d'ambiente!")
        return {}
        
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

def format_article_html(product):
    """Crea il codice HTML dell'articolo pronto per la pubblicazione"""
    # product è una tupla: (id, asin, title, price, target, img, ai_sentiment, status, last_checked)
    # Indici: 1=asin, 2=title, 3=price, 5=img, 6=ai_sentiment
    
    asin = product[1]
    title = product[2]
    price = product[3]
    image = product[5]
    ai_text = product[6] # Testo generato da GPT
    
    # URL Affiliato con Tag e Tracking
    affiliate_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"

    # Se l'AI non ha scritto nulla (caso raro), mettiamo un fallback
    if not ai_text:
        ai_text = "<p><em>Stiamo completando l'analisi dettagliata di questo prodotto. Torna a trovarci a breve per la recensione completa.</em></p>"

    # Costruzione HTML
    html = f"""
    <div style="background-color: #fff; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
            
            <div style="flex: 1; min-width: 200px; text-align: center;">
                <a href="{affiliate_link}" rel="nofollow sponsored" target="_blank">
                    <img src="{image}" alt="{title}" style="max-width: 100%; height: auto; max-height: 250px; object-fit: contain;">
                </a>
            </div>

            <div style="flex: 1.5; min-width: 250px;">
                <h2 style="margin-top: 0; font-size: 1.4rem; color: #2c3e50;">{title}</h2>
                
                <div style="margin: 15px 0;">
                    <span style="font-size: 2rem; font-weight: 800; color: #B12704;">€ {price}</span>
                    <span style="display: block; font-size: 0.85rem; color: #7f8c8d; margin-top: 5px;">
                        Prezzo rilevato il: {datetime.now().strftime("%d/%m/%Y alle %H:%M")}
                    </span>
                </div>

                <a href="{affiliate_link}" rel="nofollow sponsored" target="_blank" 
                   style="display: inline-block; background-color: #ff9900; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 1.1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                   👉 Vedi Offerta su Amazon
                </a>
            </div>
        </div>
    </div>

    <div class="rd-review-content" style="font-family: sans-serif; line-height: 1.6; color: #333;">
        {ai_text}
    </div>

    <hr style="margin: 40px 0; border: 0; border-top: 1px solid #eee;">
    
    <p style="font-size: 0.75rem; color: #95a5a6; text-align: center; font-style: italic;">
        RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU, un programma di affiliazione che consente ai siti di percepire una commissione pubblicitaria pubblicizzando e fornendo link al sito Amazon.it. I prezzi e la disponibilità dei prodotti sono accurati alla data/ora indicata e sono soggetti a modifica.
    </p>
    """
    return html

def run_publisher():
    print("🔌 [WP] Connessione al Database per cercare bozze...")
    
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 1. CERCHIAMO I PRODOTTI CON STATUS 'draft'
        # Assicurati che nel DB la colonna status sia 'draft' per i nuovi prodotti
        cursor.execute("SELECT * FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        if not products:
            print("💤 [WP] Nessuna bozza in attesa. Tutto aggiornato.")
            return

        print(f"🚀 [WP] Trovati {len(products)} articoli pronti per la pubblicazione!")

        for p in products:
            p_id = p[0] # ID Database
            title = p[2]
            
            print(f"   > Pubblicazione su WordPress: {title[:40]}...")

            post_data = {
                'title': f"Recensione: {title}",
                'content': format_article_html(p),
                'status': 'draft', # Mettiamo 'draft' su WP per tua revisione, oppure 'publish' per diretta
                # 'categories': [1], # Decommenta se sai l'ID della categoria (es. Recensioni)
                'comment_status': 'open'
            }

            try:
                response = requests.post(WP_URL, headers=get_headers(), json=post_data)

                if response.status_code == 201:
                    print("     ✅ PUBBLICATO CON SUCCESSO!")
                    
                    # 2. AGGIORNIAMO LO STATO NEL DB LOCALE A 'published'
                    # Così non viene ripubblicato al prossimo giro
                    cursor.execute("UPDATE products SET status = 'published' WHERE id = %s", (p_id,))
                    conn.commit()
                else:
                    print(f"     ❌ Errore API WP ({response.status_code}): {response.text}")
            
            except Exception as e:
                print(f"     ❌ Errore di connessione a WP: {e}")

    except mysql.connector.Error as err:
        print(f"❌ Errore Connessione DB: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("🔒 [WP] Connessione DB chiusa.")

if __name__ == "__main__":
    # Test manuale se lanciato singolarmente
    run_publisher()