import mysql.connector
import requests
import base64
import os
import time
import re

DB_CONFIG = {
    'user': 'root',
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL',
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def recover_ids_v2():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Prendi solo quelli rimasti a 0
    cursor.execute("SELECT id, asin, title FROM products WHERE status = 'published' AND (wp_post_id = 0 OR wp_post_id IS NULL)")
    missing = cursor.fetchall()
    
    if not missing:
        print("✅ Tutti gli ID sono stati recuperati!")
        return

    headers = get_headers()
    for p_id, asin, title in missing:
        # Pulizia titolo: prendiamo solo le prime 5 parole per la ricerca
        short_title = " ".join(title.split()[:5])
        print(f"📡 Ricerca avanzata per: {short_title}...")
        
        params = {'search': short_title, 'per_page': 10}
        try:
            resp = requests.get(f"{WP_API_URL}/posts", headers=headers, params=params)
            if resp.status_code == 200:
                posts = resp.json()
                found = False
                for wp_post in posts:
                    # Verifichiamo se l'ASIN è contenuto nel testo o se il titolo è molto simile
                    wp_title = wp_post['title']['rendered']
                    if title[:20].lower() in wp_title.lower() or asin in wp_post['content']['rendered']:
                        wp_id = wp_post['id']
                        cursor.execute("UPDATE products SET wp_post_id = %s WHERE id = %s", (wp_id, p_id))
                        conn.commit()
                        print(f"   ✅ AGGANCIATO: {wp_id}")
                        found = True
                        break
                if not found: print(f"   ❌ Ancora nessun match.")
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ Errore: {e}")

    conn.close()
    print("🚀 Fine recupero avanzato.")

if __name__ == "__main__":
    recover_ids_v2()