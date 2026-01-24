import mysql.connector
import requests
import base64
import os
import json
import re
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
AMAZON_TAG = "recensionedi-21"

def get_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}

def clean_amazon_image_url(url):
    """Pulisce l'URL immagine Amazon per avere l'alta risoluzione."""
    if not url or not isinstance(url, str): return ""
    # Rimuove la parte di ridimensionamento (es. ._AC_SX679_)
    return re.sub(r'\._[A-Z0-9,_\-]+_\.', '.', url)

def upload_image_to_wp(image_url, title):
    if not image_url or not image_url.startswith('http'): return None
    hd_url = clean_amazon_image_url(image_url)
    try:
        img_data = requests.get(hd_url, timeout=10).content
        file_name = f"{re.sub(r'[^a-zA-Z0-9]', '-', title.lower())[:50]}.jpg"
        headers = get_headers()
        headers['Content-Type'] = 'image/jpeg'
        headers['Content-Disposition'] = f'attachment; filename={file_name}'
        
        resp = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_data)
        if resp.status_code == 201:
            return resp.json().get('id')
    except Exception as e:
        print(f"   ⚠️ Errore upload immagine: {e}")
    return None

def run_publisher():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Seleziona prodotti in stato 'draft' pronti per WP
    cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
    products = cursor.fetchall()
    
    print(f"📮 Trovati {len(products)} articoli da pubblicare...")

    for p in products:
        try:
            print(f"   🚀 Pubblicazione: {p[2][:30]}...")
            
            # 1. Upload Immagine
            media_id = upload_image_to_wp(p[4], p[2])
            
            # 2. Parsing Dati AI
            ai_data = json.loads(p[5]) if p[5] else {}
            body_text = ai_data.get('review_text', '')
            pro_cons_html = ai_data.get('pro_cons_html', '')
            final_verdict_html = ai_data.get('verdict_html', '')
            video_html = ""
            if ai_data.get('video_id'):
                video_html = f'<div style="margin-top: 30px; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);"><iframe src="https://www.youtube.com/embed/{ai_data["video_id"]}" width="100%" height="450" frameborder="0" allowfullscreen></iframe></div>'

            # 3. COSTRUZIONE BOX PREZZO (LAYOUT FLEXBOX RICHIESTO)
            affiliate_url = f"https://www.amazon.it/dp/{p[1]}?tag={AMAZON_TAG}"
            today_date = datetime.now().strftime('%d/%m/%Y')
            
            # HTML ESATTO RICHIESTO: Immagine a SX, Dati a DX
            price_box_html = f"""
<div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
    <div style="flex: 1; text-align: center; min-width: 200px;">
        <a href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored">
            <img class="lazyload" style="max-height: 250px; width: auto; object-fit: contain;" src="{clean_amazon_image_url(p[4])}" alt="{p[2]}" />
        </a>
    </div>
    <div style="flex: 1.5; min-width: 250px;">
        <h2 style="margin-top: 0; font-size: 1.4rem;">{p[2]}</h2>
        <div class="rd-price-box" style="font-size: 2rem; color: #b12704; font-weight: bold; margin: 10px 0;">€ {p[3]}</div>
        
        <div style="background: #6c757d1a; border-left: 5px solid #6c757d; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
            <div style="font-weight: bold; color: #6c757d; text-transform: uppercase; font-size: 0.85rem;">Stato Offerta</div>
            <div class="rd-status-val" style="font-size: 0.8rem; color: #555;">⚖️ Monitoraggio avviato</div>
        </div>

        <a style="background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;" href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored">
            👉 Vedi Offerta su Amazon
        </a>
        <p style="font-size: 0.8rem; color: #666; margin-top: 5px;">Prezzo aggiornato al: {today_date}</p>
    </div>
</div>
"""
            
            # Assemblaggio finale
            full_html = price_box_html + body_text + pro_cons_html + final_verdict_html + video_html
            
            # Schema.org JSON-LD
            schema_p = {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": p[2],
                "image": clean_amazon_image_url(p[4]),
                "description": p[7] if p[7] else f"Recensione completa di {p[2]}",
                "offers": {"@type": "Offer", "price": str(p[3]), "priceCurrency": "EUR", "availability": "https://schema.org/InStock"},
                "review": {
                    "@type": "Review",
                    "reviewRating": {"@type": "Rating", "ratingValue": str(ai_data.get('final_score', 8.0)), "bestRating": "10", "worstRating": "0"},
                    "author": {"@type": "Person", "name": "Redazione RD"}
                }
            }
            full_html += f'\n<script type="application/ld+json">{json.dumps(schema_p)}</script>'

            post_data = {
                'title': f"Recensione {p[2]}", # Titolo ottimizzato
                'content': full_html,
                'status': 'publish', # Pubblica direttamente
                'categories': [int(p[6]) if p[6] else 1],
                'featured_media': media_id,
                'excerpt': p[7]
            }
            
            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            
            if resp.status_code == 201:
                wp_post_id = resp.json().get('id')
                # Aggiorna DB locale
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_post_id, p[0]))
                
                # Inserisci prezzo storico iniziale
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p[0], p[3]))
                conn.commit()
                print(f"      ✅ Pubblicato ID: {wp_post_id}")
            else:
                print(f"      ❌ Errore WP: {resp.text}")
                
        except Exception as e:
            print(f"      ❌ Errore Loop Publisher: {e}")

    conn.close()

if __name__ == "__main__":
    run_publisher()