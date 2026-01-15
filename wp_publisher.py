import mysql.connector
import requests
import base64
import os
import json
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
    if not WP_APP_PASSWORD: return {}
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }

def run_publisher():
    print("🔌 [WP] Controllo coda pubblicazione...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        if not products:
            print("💤 [WP] Nessuna bozza.")
            return

        for p in products:
            p_id = p[0]
            asin = p[1]
            title = p[2]
            price = p[3]
            image_url = p[5]
            ai_data_raw = p[6]
            
            print(f"   > Pubblicazione: {title[:30]}...")

            # 1. RECUPERO DATI AI (JSON)
            score = 85
            pros = []
            cons = []
            body_content = ""
            meta_desc = ""

            try:
                if ai_data_raw:
                    ai_data = json.loads(ai_data_raw)
                    body_content = ai_data.get('review_content', '')
                    score = int(ai_data.get('final_score', 85))
                    pros = ai_data.get('pros', [])
                    cons = ai_data.get('cons', [])
                    meta_desc = ai_data.get('meta_desc', '')
            except Exception as e:
                print(f"     ⚠️ Errore parsing JSON AI: {e}")
                body_content = ai_data_raw # Fallback testo grezzo

            # 2. CREAZIONE HTML ARTICOLO
            aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
            
            html_final = f"""
            <div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <div style="display: flex; gap: 20px; align-items: center; flex-wrap: wrap;">
                    <div style="flex: 1; text-align: center; min-width: 200px;">
                        <a href="{aff_link}" rel="nofollow sponsored" target="_blank">
                            <img src="{image_url}" style="max-height: 250px; width: auto;">
                        </a>
                    </div>
                    <div style="flex: 1.5; min-width: 250px;">
                        <h2 style="margin-top:0;">{title}</h2>
                        <div style="font-size: 2.2rem; color: #B12704; font-weight: bold; margin: 10px 0;">€ {price}</div>
                        <p style="font-size: 0.8rem; color: #666;">Rilevato il: {datetime.now().strftime("%d/%m/%Y")}</p>
                        <a href="{aff_link}" rel="nofollow sponsored" target="_blank" 
                           style="background: #ff9900; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 1.1rem;">
                           👉 Vedi Offerta su Amazon
                        </a>
                    </div>
                </div>
            </div>

            <div class="rd-review-body">
                {body_content}
            </div>

            [lets_review]
            
            <hr>
            <p style="font-size: 0.7rem; color: #999; text-align: center;">RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU.</p>
            """

            # 3. PREPARAZIONE PAYLOAD (META SBLOCCATI)
            meta_payload = {
                '_lets_review_on_off': '1',
                '_lets_review_final_score': score, # Es. 92
                '_lets_review_pros': pros,         # Es. ["Veloce", "Economico"]
                '_lets_review_cons': cons          # Es. ["Batteria scarsa"]
            }

            post_data = {
                'title': f"Recensione: {title}",
                'content': html_final,
                'status': 'draft',
                'excerpt': meta_desc,
                'meta': meta_payload 
            }

            try:
                response = requests.post(WP_URL, headers=get_headers(), json=post_data)
                
                if response.status_code == 201:
                    print(f"     ✅ Pubblicato (ID: {response.json()['id']}) con Box Let's Review!")
                    cursor.execute("UPDATE products SET status = 'published' WHERE id = %s", (p_id,))
                    conn.commit()
                else:
                    print(f"     ❌ Errore WP {response.status_code}: {response.text}")
            
            except Exception as e:
                print(f"     ❌ Errore Network: {e}")

    except Exception as err:
        print(f"❌ Errore Gen: {err}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()