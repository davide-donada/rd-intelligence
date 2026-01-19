import mysql.connector
import requests
import base64
import os
import json
from datetime import datetime

# CONFIGURAZIONE
DB_CONFIG = {
    'user': 'root', 'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'), 'port': 3306, 'database': 'recensionedigitale'
}
WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER', 'davide')
WP_APP_PASSWORD = os.getenv('WP_PASSWORD')

def get_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json'}

def upload_image_to_wp(image_url, title):
    if not image_url: return None
    try:
        img_resp = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        if img_resp.status_code != 200: return None
        filename = f"{title.replace(' ', '-').lower()[:50]}.jpg"
        token = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode())
        headers = {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Disposition': f'attachment; filename={filename}', 'Content-Type': 'image/jpeg'}
        wp_resp = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_resp.content)
        if wp_resp.status_code == 201: return wp_resp.json()['id']
    except: pass
    return None

def generate_scorecard_html(score, badge, sub_scores):
    # (Identica a prima - per brevità non la ricopio tutta, 
    # ma TU LASCIA TUTTO IL CODICE DELLA SCORECARD QUI)
    badge_color = "#28a745" if score >= 7 else "#ffc107"
    if score < 5: badge_color = "#dc3545"

    bars_html = ""
    for item in sub_scores:
        val = item['value']
        percent = val * 10
        bars_html += f"""
        <div style="margin-bottom: 10px;">
            <div style="display:flex; justify-content:space-between; font-size:0.9rem; font-weight:600; margin-bottom:5px;">
                <span>{item['label']}</span>
                <span>{val}/10</span>
            </div>
            <div style="background:#eee; border-radius:10px; height:10px; width:100%; overflow:hidden;">
                <div class="rd-bar" style="width:0%; height:100%; background: linear-gradient(90deg, {badge_color} 0%, {badge_color}aa 100%); border-radius:10px; animation: loadBar 1.5s ease-out forwards;" data-width="{percent}%"></div>
            </div>
        </div>
        """

    css_style = f"""
    <style>
        @keyframes loadBar {{ from {{ width: 0%; }} to {{ width: var(--target-width); }} }}
        .rd-bar {{ --target-width: 0%; }} 
        .rd-faq-details {{ border-bottom: 1px solid #eee; padding: 15px 0; }}
        .rd-faq-details summary {{ font-weight: bold; cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; }}
        .rd-faq-details summary::after {{ content: '+'; font-size: 1.2rem; color: #ff9900; }}
        .rd-faq-details[open] summary::after {{ content: '-'; }}
        .rd-faq-content {{ padding-top: 10px; color: #555; font-size: 0.95rem; line-height: 1.6; }}
    </style>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            var bars = document.querySelectorAll('.rd-bar');
            bars.forEach(function(bar) {{
                bar.style.setProperty('--target-width', bar.getAttribute('data-width'));
            }});
        }});
    </script>
    """

    card_html = f"""
    {css_style}
    <div style="background: #fdfdfd; border: 1px solid #eee; border-radius: 12px; padding: 25px; margin: 30px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid #eee; padding-bottom:15px;">
            <div>
                <span style="background:{badge_color}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; text-transform:uppercase; font-size:0.8rem; letter-spacing:1px;">{badge}</span>
                <h3 style="margin: 10px 0 0 0; font-size: 1.5rem;">Verdetto Finale</h3>
            </div>
            <div style="background:{badge_color}1a; color:{badge_color}; width:70px; height:70px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.8rem; font-weight:bold; border: 2px solid {badge_color};">
                {score}
            </div>
        </div>
        <div>{bars_html}</div>
    </div>
    """
    return card_html

def generate_faq_html(faqs):
    """Genera HTML a fisarmonica e JSON-LD per le FAQ"""
    if not faqs: return "", ""
    
    html_out = '<div style="margin-top: 40px;"><h2>Domande Frequenti</h2>'
    schema_items = []

    for f in faqs:
        q = f['question']
        a = f['answer']
        
        # HTML visibile
        html_out += f"""
        <details class="rd-faq-details">
            <summary>{q}</summary>
            <div class="rd-faq-content">{a}</div>
        </details>
        """
        
        # Dato per Schema.org
        schema_items.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": a
            }
        })

    html_out += "</div>"
    
    # Costruzione Schema JSON-LD FAQPage
    schema_json = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": schema_items
    }
    
    script_tag = f'\n<script type="application/ld+json">{json.dumps(schema_json)}</script>'
    
    return html_out, script_tag

def format_article_html(product, local_image_url=None, ai_data=None):
    asin = product[1]
    title = product[2]
    price = product[3]
    amazon_image_url = product[5]
    
    # Estrazione Dati
    html_body = ai_data.get('html_content', product[6]) if ai_data else product[6]
    score = ai_data.get('final_score', 8.0) if ai_data else 8.0
    badge = ai_data.get('verdict_badge', 'Consigliato') if ai_data else 'Consigliato'
    sub_scores = ai_data.get('sub_scores', [{'label':'Qualità', 'value':8}]) if ai_data else [{'label':'Qualità', 'value':8}]
    faqs = ai_data.get('faqs', []) if ai_data else []

    final_image = local_image_url if local_image_url else amazon_image_url
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"

    # Header
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

    # Blocchi
    scorecard_html = generate_scorecard_html(score, badge, sub_scores)
    faq_html, faq_schema = generate_faq_html(faqs)
    
    footer_html = """<hr style="margin: 40px 0;"><p style="font-size: 0.75rem; color: #999; text-align: center;">RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU.</p>"""
    
    # Assembliamo TUTTO: Header + Recensione + Scorecard + FAQ + Footer + Schema FAQ
    return header_html + html_body + scorecard_html + faq_html + footer_html + faq_schema

def run_publisher():
    # ... (Stesso codice di prima, nessuna modifica necessaria qui perché richiama format_article_html) ...
    # Ricordati di copiare la funzione run_publisher dal file precedente o lasciarla invariata.
    # Per sicurezza te la rimetto qui sotto completa per copia-incolla facile.
    print("🔌 [WP] Controllo coda pubblicazione...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'"
        cursor.execute(query)
        products = cursor.fetchall()
        
        if not products:
            print("💤 [WP] Nessuna bozza.")
            return

        for p in products:
            try:
                ai_data = json.loads(p[5]) 
            except:
                ai_data = {"html_content": p[5]}

            p_id = p[0]
            title = p[2]
            amazon_img = p[4]
            cat_id = p[6]
            meta_desc = p[7]

            print(f"   > Pubblicazione: {title[:30]}...")

            media_id = upload_image_to_wp(amazon_img, title)
            local_img_url = None
            if media_id:
                try:
                    media_info = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers()).json()
                    local_img_url = media_info['source_url']
                except: pass

            product_tuple = list(p)
            post_content = format_article_html(product_tuple, local_img_url, ai_data)
            
            # Schema Product
            final_score = ai_data.get('final_score', 8.0)
            schema_product = {
                "@context": "https://schema.org/", "@type": "Product", "name": title.replace('"', ''),
                "review": { "@type": "Review", "reviewRating": { "@type": "Rating", "ratingValue": str(final_score), "bestRating": "10", "worstRating": "0" }, 
                "author": { "@type": "Person", "name": "Redazione RD" }, "reviewBody": meta_desc }
            }
            # Aggiungiamo Schema Product al content (FAQ Schema è già stato aggiunto da generate_faq_html)
            post_content += f'\n<script type="application/ld+json">{json.dumps(schema_product)}</script>'

            if not meta_desc: meta_desc = f"Recensione di {title}"

            post_data = {
                'title': f"Recensione: {title}",
                'content': post_content,
                'status': 'draft',
                'categories': [cat_id],
                'featured_media': media_id if media_id else 0,
                'excerpt': meta_desc
            }

            try:
                response = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
                if response.status_code == 201:
                    print(f"     ✅ Pubblicato ID: {response.json()['id']}")
                    cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (response.json()['id'], p_id))
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