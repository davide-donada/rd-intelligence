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
        # Nome file SEO friendly
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

# --- GENERATORI HTML COMPONENTI ---

def generate_pro_cons_html(pros_list, cons_list):
    """Genera l'HTML per i box Pro e Contro affiancati."""
    # Crea le liste LI
    pros_li = "".join([f'<li style="margin-bottom: 10px; list-style: none; padding-left: 28px; position: relative; line-height: 1.5;"><span style="position: absolute; left: 0; top: 0; color: #10b981; font-weight: bold;">✓</span>{item}</li>' for item in pros_list])
    cons_li = "".join([f'<li style="margin-bottom: 10px; list-style: none; padding-left: 28px; position: relative; line-height: 1.5;"><span style="position: absolute; left: 0; top: 0; color: #ef4444; font-weight: bold;">✕</span>{item}</li>' for item in cons_list])

    return f"""
<div style="display: flex; flex-wrap: wrap; gap: 25px; margin: 40px 0;">
    <div style="flex: 1; min-width: 300px; background: #ffffff; border-top: 4px solid #10b981; border-radius: 8px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <h3 style="margin-top: 0; color: #065f46; font-size: 1.3rem; border-bottom: 1px solid #ecfdf5; padding-bottom: 10px; margin-bottom: 15px;">PRO</h3>
        <ul style="margin: 0; padding: 0; color: #374151;">{pros_li}</ul>
    </div>
    <div style="flex: 1; min-width: 300px; background: #ffffff; border-top: 4px solid #ef4444; border-radius: 8px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <h3 style="margin-top: 0; color: #991b1b; font-size: 1.3rem; border-bottom: 1px solid #fef2f2; padding-bottom: 10px; margin-bottom: 15px;">CONTRO</h3>
        <ul style="margin: 0; padding: 0; color: #374151;">{cons_li}</ul>
    </div>
</div>
"""

def generate_verdict_html(score, badge, sub_scores):
    """Genera il box del verdetto finale con barre di progresso."""
    bars_html = ""
    for item in sub_scores:
        val = item.get('value', 8)
        label = item.get('label', 'Generale')
        # Calcolo larghezza barra
        width_pct = min(max(val * 10, 0), 100)
        
        bars_html += f"""
        <div style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: bold; margin-bottom: 6px; color: #4b5563;">{label} {val}</div>
            <div style="background: #f3f4f6; border-radius: 99px; height: 10px; width: 100%; overflow: hidden;">
                <div style="width: {width_pct}%; height: 100%; background: linear-gradient(135deg, #10b981 0%, #34d399 100%); border-radius: 99px;"></div>
            </div>
        </div>"""

    return f"""
<div style="background: #ffffff; border-radius: 16px; padding: 30px; margin: 40px 0; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); border: 1px solid #f3f4f6;">
    <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 30px;">
        <div style="flex: 0 0 auto; text-align: center; min-width: 120px; margin: 0 auto;">
            <div style="width: 100px; height: 100px; border-radius: 50%; background: linear-gradient(135deg, #10b981 0%, #34d399 100%); display: flex; align-items: center; justify-content: center; color: white; font-size: 2.5rem; font-weight: 800; box-shadow: 0 10px 15px -3px rgba(16, 185, 129, 0.4); margin: 0 auto 15px auto;">{score}</div>
            <div style="background: #10b9811a; color: #10b981; display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; text-transform: uppercase;">{badge}</div>
        </div>
        <div style="flex: 1; min-width: 250px;">
            <h3 style="margin: 0 0 20px 0; font-size: 1.5rem; color: #111827; border-bottom: 2px solid #f3f4f6; padding-bottom: 10px;">Verdetto Finale</h3>
            {bars_html}
        </div>
    </div>
</div>
"""

# --- FUNZIONE PRINCIPALE ---

def run_publisher():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Seleziona prodotti pronti (draft)
    cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
    products = cursor.fetchall()
    
    print(f"📮 Trovati {len(products)} articoli da pubblicare...")

    for p in products:
        try:
            p_id, asin, title, price, img_url, ai_json, cat_id, meta_desc = p
            print(f"   🚀 Pubblicazione: {title[:30]}...")
            
            # 1. Caricamento Immagine
            media_id = upload_image_to_wp(img_url, title)
            
            # 2. Parsing Dati AI
            ai_data = json.loads(ai_json) if ai_json else {}
            
            # --- COSTRUZIONE CONTENUTO ---
            
            # A. Box Prezzo (NUOVO LAYOUT FLEXBOX)
            affiliate_url = f"https://www.amazon.it/dp/{asin}?tag={AMAZON_TAG}"
            today_date = datetime.now().strftime('%d/%m/%Y')
            clean_img = clean_amazon_image_url(img_url)
            
            price_box_html = f"""
<div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
    <div style="flex: 1; text-align: center; min-width: 200px;">
        <a href="{affiliate_url}" target="_blank" rel="nofollow noopener sponsored">
            <img class="lazyload" style="max-height: 250px; width: auto; object-fit: contain;" src="{clean_img}" alt="{title}" />
        </a>
    </div>
    <div style="flex: 1.5; min-width: 250px;">
        <h2 style="margin-top: 0; font-size: 1.4rem;">{title}</h2>
        <div class="rd-price-box" style="font-size: 2rem; color: #b12704; font-weight: bold; margin: 10px 0;">€ {price}</div>
        
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

            # B. Testo Recensione
            review_text = ai_data.get('review_text', '')
            if not review_text: review_text = "<p>Recensione in aggiornamento...</p>"
            
            # C. Video YouTube (se presente nel JSON AI)
            video_html = ""
            if ai_data.get('video_id'):
                video_html = f'<div style="margin: 30px 0; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);"><iframe src="https://www.youtube.com/embed/{ai_data["video_id"]}" width="100%" height="450" frameborder="0" allowfullscreen></iframe></div>'

            # D. Pro e Contro
            pro_cons_html = generate_pro_cons_html(
                ai_data.get('pro_cons', {}).get('pros', []), 
                ai_data.get('pro_cons', {}).get('cons', [])
            )
            
            # E. Verdetto Finale
            verdict_html = generate_verdict_html(
                ai_data.get('final_score', 8.0),
                ai_data.get('verdict_badge', 'Buono'),
                ai_data.get('sub_scores', [])
            )

            # Assemblaggio Finale
            full_html = price_box_html + review_text + video_html + pro_cons_html + verdict_html
            
            # F. Schema.org JSON-LD
            schema_p = {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": title,
                "image": clean_img,
                "description": meta_desc,
                "offers": {"@type": "Offer", "price": str(price), "priceCurrency": "EUR", "availability": "https://schema.org/InStock"},
                "review": {
                    "@type": "Review",
                    "reviewRating": {"@type": "Rating", "ratingValue": str(ai_data.get('final_score', 8.0)), "bestRating": "10", "worstRating": "0"},
                    "author": {"@type": "Person", "name": "Redazione RD"}
                }
            }
            full_html += f'\n<script type="application/ld+json">{json.dumps(schema_p)}</script>'

            # 4. Invio a WordPress
            post_data = {
                'title': f"Recensione: {title}",
                'content': full_html,
                'status': 'publish', # Pubblica direttamente
                'categories': [int(cat_id) if cat_id else 1],
                'featured_media': media_id,
                'excerpt': meta_desc
            }
            
            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            
            if resp.status_code == 201:
                wp_post_id = resp.json().get('id')
                
                # Aggiorna DB locale
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_post_id, p_id))
                
                # Inserisci prezzo storico iniziale
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, price))
                conn.commit()
                print(f"      ✅ Pubblicato Articolo ID: {wp_post_id}")
            else:
                print(f"      ❌ Errore API WP: {resp.text}")
                
        except Exception as e:
            print(f"      ❌ Errore Loop Publisher: {e}")

    conn.close()

if __name__ == "__main__":
    run_publisher()