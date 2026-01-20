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
WP_AUTHOR_ID = os.getenv('WP_AUTHOR_ID')

def get_headers():
    if not WP_APP_PASSWORD: return {}
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }

def clean_amazon_image_url(url):
    if not url or not isinstance(url, str): return ""
    try:
        clean_url = re.sub(r'\._AC_.*_\.', '.', url)
        return clean_url
    except:
        return url

def upload_image_to_wp(image_url, title):
    if not image_url or not isinstance(image_url, str) or not image_url.startswith('http'):
        return None
    
    print(f"   📸 Scarico IMG: {title[:20]}...")
    try:
        img_resp = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if img_resp.status_code != 200: return None
        
        safe_title = re.sub(r'[^a-zA-Z0-9]', '-', title)
        safe_title = re.sub(r'-+', '-', safe_title).strip('-')
        filename = f"{safe_title.lower()[:50]}.jpg"
        
        credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
        token = base64.b64encode(credentials.encode())
        media_headers = {
            'Authorization': f'Basic {token.decode("utf-8")}',
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'image/jpeg'
        }

        wp_resp = requests.post(f"{WP_API_URL}/media", headers=media_headers, data=img_resp.content)
        if wp_resp.status_code == 201:
            return wp_resp.json()['id']
    except Exception as e:
        print(f"     ⚠️ Errore upload: {e}")
    return None

# --- ANALISI PREZZO (LOGICA KEEPA) ---
def analyze_price_history(product_id, current_price):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 30", (product_id,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "⚖️ Prezzo Standard", "#6c757d", "Analisi in corso..."

        prices = [float(r[0]) for r in rows]
        prices.append(float(current_price))
        
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        current = float(current_price)

        if current <= min_price:
            return "🔥 OTTIMO PREZZO", "#28a745", "Minimo storico rilevato!"
        elif current < avg_price:
            return "✅ BUON PREZZO", "#17a2b8", "Sotto la media."
        elif current > (avg_price * 1.1):
            return "⚠️ PREZZO ALTO", "#dc3545", "Consigliamo di aspettare."
        else:
            return "⚖️ PREZZO MEDIO", "#ffc107", "In linea con il mercato."
    except:
        return "⚖️ Prezzo Standard", "#6c757d", ""

def generate_scorecard_html(score, badge, sub_scores):
    badge_color = "#28a745"
    if score < 7: badge_color = "#ffc107"
    if score < 5: badge_color = "#dc3545"

    bars_html = ""
    for item in sub_scores:
        val = item.get('value', 8)
        label = item.get('label', 'Qualità')
        percent = val * 10
        bars_html += f"""
        <div style="margin-bottom: 10px;">
            <div style="display:flex; justify-content:space-between; font-size:0.9rem; font-weight:600; margin-bottom:5px;">
                <span>{label}</span>
                <span>{val}/10</span>
            </div>
            <div style="background:#eee; border-radius:10px; height:10px; width:100%; overflow:hidden;">
                <div class="rd-bar" style="width:0%; height:100%; background: linear-gradient(90deg, {badge_color} 0%, {badge_color}aa 100%); border-radius:10px; animation: loadBar 1.5s ease-out forwards;" data-width="{percent}%"></div>
            </div>
        </div>
        """
    css_minified = """<style>@keyframes loadBar{from{width:0%}to{width:var(--target-width)}}.rd-bar{--target-width:0%}.rd-faq-details{border-bottom:1px solid #eee!important;padding:15px 0!important;margin:0!important}.rd-faq-details summary{font-weight:700!important;cursor:pointer!important;list-style:none!important;display:flex!important;justify-content:space-between!important;align-items:center!important;font-size:1.1rem!important;color:#222!important;outline:none!important;background:0 0!important}.rd-faq-details summary::-webkit-details-marker{display:none!important}.rd-faq-details summary::after{content:'+'!important;font-size:1.5rem!important;color:#ff9900!important;font-weight:300!important}.rd-faq-details[open] summary::after{content:'-'!important;color:#B12704!important}.rd-faq-content{padding-top:15px!important;color:#555!important;font-size:.95rem!important;line-height:1.6!important}</style>"""
    js_script = """<script>document.addEventListener("DOMContentLoaded", function(){var bars=document.querySelectorAll('.rd-bar');bars.forEach(function(bar){bar.style.setProperty('--target-width', bar.getAttribute('data-width'));});});</script>"""
    return f"{css_minified}{js_script}<div style='background: #fdfdfd; border: 1px solid #eee; border-radius: 12px; padding: 25px; margin: 30px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.05);'><div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid #eee; padding-bottom:15px;'><div><span style='background:{badge_color}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; text-transform:uppercase; font-size:0.8rem; letter-spacing:1px;'>{badge}</span><h3 style='margin: 10px 0 0 0; font-size: 1.5rem;'>Verdetto Finale</h3></div><div style='background:{badge_color}1a; color:{badge_color}; width:70px; height:70px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.8rem; font-weight:bold; border: 2px solid {badge_color};'>{score}</div></div><div>{bars_html}</div></div>"

def generate_faq_html(faqs):
    if not faqs: return "", ""
    html_out = '<div style="margin-top: 40px;"><h2>Domande Frequenti</h2>'
    schema_items = []
    for f in faqs:
        q = f.get('question', '')
        a = f.get('answer', '')
        html_out += f"<details class='rd-faq-details'><summary>{q}</summary><div class='rd-faq-content'>{a}</div></details>"
        schema_items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    html_out += "</div>"
    schema_json = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": schema_items}
    return html_out, f'\n<script type="application/ld+json">{json.dumps(schema_json)}</script>'

def format_article_html(product, local_image_url=None, ai_data=None):
    product_id = product[0]
    asin = product[1]
    title = product[2]
    price = product[3]
    
    if local_image_url and isinstance(local_image_url, str) and local_image_url.startswith('http'):
        final_image = local_image_url
    else:
        final_image = clean_amazon_image_url(product[5])
    
    html_body = ai_data.get('html_content', 'Recensione in lavorazione...')
    score = ai_data.get('final_score', 8.0)
    badge = ai_data.get('verdict_badge', 'Consigliato')
    sub_scores = ai_data.get('sub_scores', [])
    faqs = ai_data.get('faqs', [])
    video_id = ai_data.get('video_id', None) # Se è nel JSON lo usiamo
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"

    # Analisi Prezzo
    p_verdict, p_color, p_desc = analyze_price_history(product_id, price)
    price_widget = f"""<div style="background:{p_color}1a; border-left: 5px solid {p_color}; padding: 10px 15px; margin: 10px 0; border-radius: 4px;"><div style="font-weight: bold; color: {p_color}; text-transform: uppercase; font-size: 0.85rem;">{p_verdict}</div><div style="font-size: 0.8rem; color: #555;">{p_desc}</div></div>"""

    header_html = f"<div style='background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;'><div style='flex: 1; text-align: center; min-width: 200px;'><a href='{aff_link}' rel='nofollow sponsored' target='_blank'><img src='{final_image}' alt='{title}' style='max-height: 250px; width: auto; object-fit: contain;'></a></div><div style='flex: 1.5; min-width: 250px;'><h2 style='margin-top: 0; font-size: 1.4rem;'>{title}</h2><div style='font-size: 2rem; color: #B12704; font-weight: bold; margin: 10px 0;'>€ {price}</div>{price_widget}<a href='{aff_link}' rel='nofollow sponsored' target='_blank' style='background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px;'>👉 Vedi Offerta su Amazon</a><p style='font-size: 0.8rem; color: #666; margin-top: 5px;'>Prezzo aggiornato al: {datetime.now().strftime('%d/%m/%Y')}</p></div></div>"

    video_html = ""
    if video_id:
        video_html = f"<div style='margin: 40px 0;'><h3>🎥 Video Recensione Selezionata</h3><div style='position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);'><iframe src='https://www.youtube.com/embed/{video_id}' style='position: absolute; top: 0; left: 0; width: 100%; height: 100%;' frameborder='0' allowfullscreen></iframe></div></div>"

    scorecard_html = generate_scorecard_html(score, badge, sub_scores)
    faq_html, faq_schema = generate_faq_html(faqs)
    footer_html = "<hr style='margin: 40px 0;'><p style='font-size: 0.75rem; color: #999; text-align: center;'>RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU.</p>"

    return header_html + html_body + scorecard_html + video_html + faq_html + footer_html + faq_schema

def run_publisher():
    print("🔌 [WP] Controllo bozze...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # Selezioniamo anche CATEGORY_ID e VIDEO_ID (se l'hai salvato in JSON ai_sentiment)
        cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        for p in products:
            try:
                ai_data = json.loads(p[5]) 
            except:
                ai_data = {"html_content": p[5]}

            print(f"   > Pubblicazione: {p[2][:30]}...")
            
            # --- FIX CATEGORIA ---
            cat_id = p[6] # Colonna category_id dal DB
            if cat_id is None: 
                cat_id = 1
            
            # Forziamo a intero per WordPress
            try:
                cat_id = int(cat_id)
            except:
                cat_id = 1
            
            print(f"     📂 Categoria per WP: {cat_id}")

            hd_url = clean_amazon_image_url(p[4])
            media_id = upload_image_to_wp(hd_url, p[2])
            
            local_url = None
            if media_id:
                try:
                    m_info = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers()).json()
                    local_url = m_info.get('source_url')
                except: pass

            post_content = format_article_html(p, local_url, ai_data)
            
            final_score = ai_data.get('final_score', 8.0)
            schema_p = {"@context": "https://schema.org/", "@type": "Product", "name": p[2], "review": {"@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": str(final_score)}, "author": {"@type": "Person", "name": "Redazione RD"}}}
            post_content += f'\n<script type="application/ld+json">{json.dumps(schema_p)}</script>'

            # PREPARAZIONE DATI POST
            post_data = {
                'title': f"Recensione: {p[2]}",
                'content': post_content,
                'status': 'draft', 
                'categories': [cat_id], # <--- QUI ORA È SICURO UN NUMERO
                'featured_media': media_id if media_id else 0,
                'excerpt': p[7]
            }
            if WP_AUTHOR_ID: post_data['author'] = int(WP_AUTHOR_ID)

            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            if resp.status_code == 201:
                cursor.execute("UPDATE products SET status = 'published' WHERE id = %s", (p[0],))
                # INIZIALIZZAZIONE STORICO
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p[0], p[3]))
                conn.commit()
                print("     ✅ Pubblicato e Iniziato Tracking!")
            else:
                print(f"     ❌ Errore WP: {resp.text}")

    except Exception as e: print(f"❌ Errore Publisher: {e}")
    finally: 
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()