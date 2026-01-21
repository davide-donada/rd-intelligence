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

def analyze_price_history(product_id, current_price):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 30", (product_id,))
        rows = cursor.fetchall()
        conn.close()
        prices = [float(r[0]) for r in rows] if rows else [float(current_price)]
        if len(prices) < 2:
            return "⚖️ PREZZO STANDARD", "#6c757d", "Analisi di mercato avviata."
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        current = float(current_price)
        if current <= min_price:
            return "🔥 OTTIMO PREZZO", "#28a745", "Minimo storico rilevato!"
        elif current < avg_price:
            return "✅ BUON PREZZO", "#17a2b8", "Sotto la media recente."
        else:
            return "⚖️ PREZZO MEDIO", "#ffc107", "In linea con il prezzo di mercato."
    except:
        return "⚖️ PREZZO STANDARD", "#6c757d", ""

def format_article_html(product, local_image_url=None, ai_data=None):
    product_id, asin, title, price, img_orig = product[0], product[1], product[2], product[3], product[4]
    final_image = local_image_url if local_image_url else clean_amazon_image_url(product[5])
    html_body = ai_data.get('html_content', 'Contenuto in generazione...')
    score = ai_data.get('final_score', 8.0)
    badge = ai_data.get('verdict_badge', 'Consigliato')
    sub_scores = ai_data.get('sub_scores', [])
    faqs = ai_data.get('faqs', [])
    video_id = ai_data.get('video_id', None)
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    p_verdict, p_color, p_desc = analyze_price_history(product_id, price)
    price_widget = f"""<div style="background:{p_color}1a; border-left: 5px solid {p_color}; padding: 10px 15px; margin: 10px 0; border-radius: 4px;"><div style="font-weight: bold; color: {p_color}; text-transform: uppercase; font-size: 0.85rem;">{p_verdict}</div><div style="font-size: 0.8rem; color: #555;">{p_desc}</div></div>"""
    header_html = f"<div style='background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;'><div style='flex: 1; text-align: center; min-width: 200px;'><a href='{aff_link}' rel='nofollow sponsored' target='_blank'><img src='{final_image}' alt='{title}' style='max-height: 250px; width: auto; object-fit: contain;'></a></div><div style='flex: 1.5; min-width: 250px;'><h2 style='margin-top: 0; font-size: 1.4rem;'>{title}</h2><div style='font-size: 2rem; color: #B12704; font-weight: bold; margin: 10px 0;'>€ {price}</div>{price_widget}<a href='{aff_link}' rel='nofollow sponsored' target='_blank' style='background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px;'>👉 Vedi Offerta su Amazon</a><p style='font-size: 0.8rem; color: #666; margin-top: 5px;'>Prezzo aggiornato al: {datetime.now().strftime('%d/%m/%Y')}</p></div></div>"
    video_html = f"<div style='margin: 40px 0;'><h3>🎥 Video Recensione Selezionata</h3><div style='position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);'><iframe src='https://www.youtube.com/embed/{video_id}' style='position: absolute; top: 0; left: 0; width: 100%; height: 100%;' frameborder='0' allowfullscreen></iframe></div></div>" if video_id else ""
    footer_html = "<hr style='margin: 40px 0;'><p style='font-size: 0.75rem; color: #999; text-align: center;'>RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU.</p>"
    return header_html + html_body + video_html + footer_html

def run_publisher():
    print("🔌 [WP] Controllo prodotti in draft...")
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, asin, title, current_price, image_url, ai_sentiment, category_id, meta_desc FROM products WHERE status = 'draft'")
        products = cursor.fetchall()
        for p in products:
            p_id, current_price = p[0], p[3]
            cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p_id, current_price))
            conn.commit()
            ai_data = json.loads(p[5]) if isinstance(p[5], str) else p[5]
            cat_id = int(p[6]) if p[6] else 1
            hd_url = clean_amazon_image_url(p[4])
            media_id = upload_image_to_wp(hd_url, p[2])
            local_url = None
            if media_id:
                try:
                    m_info = requests.get(f"{WP_API_URL}/media/{media_id}", headers=get_headers()).json()
                    local_url = m_info.get('source_url')
                except: pass
            post_content = format_article_html(p, local_url, ai_data)
            post_data = {
                'title': f"Recensione: {p[2]}",
                'content': post_content,
                'status': 'draft', 
                'categories': [cat_id],
                'featured_media': media_id if media_id else 0,
                'excerpt': p[7]
            }
            resp = requests.post(f"{WP_API_URL}/posts", headers=get_headers(), json=post_data)
            if resp.status_code == 201:
                wp_id = resp.json().get('id')
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_id, p_id))
                conn.commit()
                print(f"     ✅ Pubblicato (WP ID: {wp_id})!")
            else:
                print(f"     ❌ Errore WP: {resp.text}")
    except Exception as e: print(f"❌ Errore Publisher: {e}")
    finally: 
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()