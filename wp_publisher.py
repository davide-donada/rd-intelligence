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

def get_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }

def clean_amazon_image_url(url):
    if not url or not isinstance(url, str): return ""
    return re.sub(r'\._[A-Z0-9,_-]+_\.', '.', url)

def upload_image_to_wp(image_url, title):
    if not image_url or not image_url.startswith('http'): return None
    hd_url = clean_amazon_image_url(image_url)
    try:
        img_resp = requests.get(hd_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        if img_resp.status_code != 200: return None
        filename = f"{re.sub(r'[^a-zA-Z0-9]', '-', title).lower()[:50]}.jpg"
        headers = get_headers()
        headers['Content-Disposition'] = f'attachment; filename={filename}'
        headers['Content-Type'] = 'image/jpeg'
        wp_resp = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_resp.content)
        return wp_resp.json()['id'] if wp_resp.status_code == 201 else None
    except: return None

def generate_pros_cons_html(pros, cons):
    if not pros and not cons: return ""
    # Font rimosso per usare quello predefinito del sito
    pros_html = "".join([f"<li style='margin-bottom:8px; list-style:none; padding-left:25px; position:relative;'><span style='position:absolute; left:0; color:#28a745;'>✅</span>{p}</li>" for p in pros])
    cons_html = "".join([f"<li style='margin-bottom:8px; list-style:none; padding-left:25px; position:relative;'><span style='position:absolute; left:0; color:#dc3545;'>❌</span>{c}</li>" for c in cons])
    return f"""
    <div style="display: flex; flex-wrap: wrap; gap: 20px; margin: 30px 0;">
        <div style="flex: 1; min-width: 280px; background: #f0fff4; border: 1px solid #c6f6d5; border-radius: 12px; padding: 20px;">
            <h3 style="margin-top: 0; color: #22543d; font-size: 1.2rem;">✅ Pro</h3>
            <ul style="margin: 0; padding: 0;">{pros_html}</ul>
        </div>
        <div style="flex: 1; min-width: 280px; background: #fff5f5; border: 1px solid #fed7d7; border-radius: 12px; padding: 20px;">
            <h3 style="margin-top: 0; color: #822727; font-size: 1.2rem;">❌ Contro</h3>
            <ul style="margin: 0; padding: 0;">{cons_html}</ul>
        </div>
    </div>"""

def generate_scorecard_html(score, badge, sub_scores):
    color = "#28a745" if score >= 7.5 else "#ffc107" if score >= 6 else "#dc3545"
    bars = "".join([f"<div style='margin-bottom:10px;'><div style='display:flex; justify-content:space-between; font-size:0.85rem; font-weight:600;'><span>{s['label']}</span><span>{s['value']}/10</span></div><div style='background:#eee; border-radius:10px; height:8px;'><div style='width:{int(s['value']*10)}%; height:100%; background:{color}; border-radius:10px;'></div></div></div>" for s in sub_scores])
    return f"<div style='background:#f9f9f9; border:1px solid #eee; border-radius:15px; padding:25px; margin:30px 0;'><div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;'><h3 style='margin:0;'>Verdetto Finale</h3><div style='background:{color}; color:white; width:50px; height:50px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold;'>{score}</div></div>{bars}</div>"

def analyze_price_history(product_id, current_price):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 30", (product_id,))
        rows = cursor.fetchall()
        conn.close()
        prices = [float(r[0]) for r in rows] if rows else [float(current_price)]
        if len(prices) < 2: return "⚖️ PREZZO STANDARD", "#6c757d", "Monitoraggio appena avviato."
        avg = sum(prices) / len(prices)
        current = float(current_price)
        if current <= min(prices): return "🔥 OTTIMO PREZZO", "#28a745", "Minimo storico rilevato!"
        return ("✅ BUON PREZZO", "#17a2b8", "Sotto la media recente.") if current < avg else ("⚖️ PREZZO MEDIO", "#ffc107", "In linea con il mercato.")
    except: return "⚖️ PREZZO STANDARD", "#6c757d", ""

def format_article_html(product, local_image_url, ai_data):
    p_id, asin, title, price = product[0], product[1], product[2], product[3]
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    
    p_verdict, p_color, p_desc = analyze_price_history(p_id, price)
    price_widget = f"<div style='border-left:4px solid {p_color}; padding-left:15px; margin:20px 0;'><strong>{p_verdict}</strong><br><small>{p_desc}</small></div>"

    header = f"<div style='text-align:center;'><a href='{aff_link}' target='_blank'><img src='{local_image_url}' style='max-height:350px;'></a><h2>{title}</h2><p style='font-size:1.5rem; color:#B12704;'><strong>€{price}</strong></p>{price_widget}<a href='{aff_link}' target='_blank' style='background:#ff9900; color:white; padding:12px 25px; text-decoration:none; border-radius:5px; font-weight:bold;'>Vedi Offerta su Amazon</a></div>"
    
    body = ai_data.get('html_content', '')
    pros_cons = generate_pros_cons_html(ai_data.get('pros', []), ai_data.get('cons', []))
    scorecard = generate_scorecard_html(ai_data.get('final_score', 8.0), ai_data.get('verdict_badge', 'Consigliato'), ai_data.get('sub_scores', []))
    
    video = f"<div style='margin-top:30px;'><iframe width='100%' height='400' src='https://www.youtube.com/embed/{ai_data.get('video_id', '')}' frameborder='0' allowfullscreen></iframe></div>" if ai_data.get('video_id') else ""
    
    return header + body + pros_cons + scorecard + video

def run_publisher():
    print("🔌 [WP] Avvio pubblicazione bozze...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
        for p in cursor.fetchall():
            ai_data = json.loads(p[5])
            media_id = upload_image_to_wp(p[4], p[2])
            
            local_url = p[4]
            if media_id:
                try:
                    resp_media = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers())
                    local_url = resp_media.json().get('source_url', p[4])
                except: pass
            
            full_html = format_article_html(p, local_url, ai_data)
            
            schema_p = {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": p[2],
                "review": {
                    "@type": "Review",
                    "reviewRating": {"@type": "Rating", "ratingValue": str(ai_data.get('final_score', 8.0)), "bestRating": "10", "worstRating": "0"},
                    "author": {"@type": "Person", "name": "Redazione RD"}
                }
            }
            full_html += f'\n<script type="application/ld+json">{json.dumps(schema_p)}</script>'

            post_data = {
                'title': f"Recensione: {p[2]}",
                'content': full_html,
                'status': 'draft',
                'categories': [int(p[6]) if p[6] else 1],
                'featured_media': media_id,
                'excerpt': p[7]
            }
            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            if resp.status_code == 201:
                wp_post_id = resp.json().get('id')
                # AGGIORNAMENTO STORICO E COLLEGAMENTO WP_POST_ID
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_post_id, p[0]))
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p[0], p[3]))
                conn.commit()
                print(f"✅ Pubblicato e Storico Avviato: {p[1]} (WP ID: {wp_post_id})")
    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()