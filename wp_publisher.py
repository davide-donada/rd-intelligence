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
    return {'Authorization': f'Basic {token.decode("utf-8")}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}

def upload_image_to_wp(image_url, title):
    if not image_url or not image_url.startswith('http'): return None
    try:
        img_resp = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if img_resp.status_code != 200: return None
        safe_title = re.sub(r'[^a-zA-Z0-9]', '-', title).lower()[:50]
        filename = f"{safe_title}.jpg"
        media_headers = get_headers()
        media_headers['Content-Disposition'] = f'attachment; filename={filename}'
        media_headers['Content-Type'] = 'image/jpeg'
        wp_resp = requests.post(f"{WP_API_URL}/media", headers=media_headers, data=img_resp.content)
        return wp_resp.json()['id'] if wp_resp.status_code == 201 else None
    except: return None

def analyze_price_history(product_id, current_price):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 30", (product_id,))
        rows = cursor.fetchall()
        conn.close()
        prices = [float(r[0]) for r in rows] if rows else [float(current_price)]
        if len(prices) < 2: return "⚖️ PREZZO STANDARD", "#6c757d", "Monitoraggio prezzi appena avviato."
        avg = sum(prices) / len(prices)
        current = float(current_price)
        if current <= min(prices): return "🔥 OTTIMO PREZZO", "#28a745", "Minimo storico rilevato!"
        return ("✅ BUON PREZZO", "#17a2b8", "Sotto la media recente.") if current < avg else ("⚖️ PREZZO MEDIO", "#ffc107", "In linea con il mercato.")
    except: return "⚖️ PREZZO STANDARD", "#6c757d", ""

def generate_scorecard_html(score, badge, sub_scores):
    badge_color = "#28a745" if score >= 7.5 else "#ffc107" if score >= 6 else "#dc3545"
    bars = ""
    for item in sub_scores:
        val = item.get('value', 0)
        percent = int(val * 10)
        bars += f"""
        <div style="margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; font-size:0.9rem; font-weight:600; margin-bottom:5px; color:#333;">
                <span>{item.get('label')}</span><span>{val}/10</span>
            </div>
            <div style="background:#eee; border-radius:10px; height:12px; width:100%; overflow:hidden;">
                <div style="width:{percent}%; height:100%; background:{badge_color}; border-radius:10px;"></div>
            </div>
        </div>"""
    return f"""<div style='background:#f9f9f9; border:1px solid #eee; border-radius:15px; padding:30px; margin:40px 0;'>
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:2px solid #eee; padding-bottom:15px;'>
            <div><span style='background:{badge_color}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; font-size:0.8rem;'>{badge}</span><h3 style='margin:10px 0 0 0; font-size:1.6rem;'>Verdetto Finale</h3></div>
            <div style='background:white; color:{badge_color}; width:65px; height:65px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.6rem; font-weight:bold; border:3px solid {badge_color};'>{score}</div>
        </div>{bars}</div>"""

def format_article_html(product, local_image_url=None, ai_data=None):
    # Indici: 0:id, 1:asin, 2:title, 3:price, 4:image_url
    p_id, asin, title, price, img_orig = product[0], product[1], product[2], product[3], product[4]
    final_img = local_image_url if local_image_url else img_orig
    video_id = ai_data.get('video_id')
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    
    p_verdict, p_color, p_desc = analyze_price_history(p_id, price)
    price_widget = f"<div style='border-left:4px solid {p_color}; padding-left:15px; margin:20px 0;'><strong>{p_verdict}</strong><br><small>{p_desc}</small></div>"
    
    header = f"<div style='text-align:center; margin-bottom:30px;'><a href='{aff_link}' target='_blank'><img src='{final_img}' style='max-height:300px;'></a><h2>{title}</h2><p style='font-size:1.8rem; color:#B12704; font-weight:bold;'>€ {price}</p>{price_widget}<a href='{aff_link}' target='_blank' style='background:#ff9900; color:white; padding:12px 25px; text-decoration:none; border-radius:5px; font-weight:bold; display:inline-block;'>Vedi Offerta su Amazon</a></div>"
    
    scorecard = generate_scorecard_html(ai_data.get('final_score', 8.0), ai_data.get('verdict_badge', 'Consigliato'), ai_data.get('sub_scores', []))
    content = ai_data.get('html_content', '')
    video = f"<div style='margin-top:40px;'><h3>🎥 Video Recensione Selezionata</h3><iframe width='100%' height='450' src='https://www.youtube.com/embed/{video_id}' frameborder='0' allowfullscreen></iframe></div>" if video_id else ""
    
    return header + content + scorecard + video

def run_publisher():
    print("🔌 [WP] Controllo prodotti in draft...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # RIMOSSO 'features' dalla query SQL
        cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        
        for p in products:
            p_id, price = p[0], p[3]
            ai_data = json.loads(p[5])
            
            # 1. Storico Prezzi
            cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, price))
            conn.commit()

            # 2. Immagine
            media_id = upload_image_to_wp(p[4], p[2])
            local_url = None
            if media_id:
                try:
                    m_info = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers()).json()
                    local_url = m_info.get('source_url')
                except: pass

            # 3. Formattazione
            full_html = format_article_html(p, local_url, ai_data)
            
            post_data = {
                'title': f"Recensione: {p[2]}",
                'content': full_html,
                'status': 'draft',
                'categories': [int(p[6]) if p[6] else 1],
                'featured_media': media_id if media_id else 0,
                'excerpt': p[7]
            }
            
            # 4. Pubblicazione
            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            if resp.status_code == 201:
                wp_id = resp.json().get('id')
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_id, p_id))
                conn.commit()
                print(f"✅ Pubblicato: {p[1]} (WP ID: {wp_id})")
            else:
                print(f"❌ Errore WP per {p[1]}: {resp.text}")

    except Exception as e: print(f"❌ Errore Publisher: {e}")
    finally: 
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()