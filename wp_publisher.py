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

def clean_amazon_image_url(url):
    if not url or not isinstance(url, str): return ""
    return re.sub(r'\._[A-Z0-9,_\-]+_\.', '.', url)

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

# --- COMPONENTI HTML ---

def generate_pros_cons_html(pros, cons):
    if not pros and not cons: return ""
    pros_html = "".join([f"<li style='margin-bottom:10px; list-style:none; padding-left:28px; position:relative; line-height:1.5;'><span style='position:absolute; left:0; top:0; color:#10b981; font-weight:bold;'>✓</span>{p}</li>" for p in pros])
    cons_html = "".join([f"<li style='margin-bottom:10px; list-style:none; padding-left:28px; position:relative; line-height:1.5;'><span style='position:absolute; left:0; top:0; color:#ef4444; font-weight:bold;'>✕</span>{c}</li>" for c in cons])
    return f"""
    <div style="display: flex; flex-wrap: wrap; gap: 25px; margin: 40px 0;">
        <div style="flex: 1; min-width: 300px; background: #ffffff; border-top: 4px solid #10b981; border-radius: 8px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <h3 style="margin-top: 0; color: #065f46; font-size: 1.3rem; border-bottom: 1px solid #ecfdf5; padding-bottom: 10px; margin-bottom: 15px;">PRO</h3>
            <ul style="margin: 0; padding: 0; color: #374151;">{pros_html}</ul>
        </div>
        <div style="flex: 1; min-width: 300px; background: #ffffff; border-top: 4px solid #ef4444; border-radius: 8px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <h3 style="margin-top: 0; color: #991b1b; font-size: 1.3rem; border-bottom: 1px solid #fef2f2; padding-bottom: 10px; margin-bottom: 15px;">CONTRO</h3>
            <ul style="margin: 0; padding: 0; color: #374151;">{cons_html}</ul>
        </div>
    </div>"""

def generate_scorecard_html(score, badge, sub_scores):
    if score >= 7.5:
        gradient = "linear-gradient(135deg, #10b981 0%, #34d399 100%)"
        primary_color = "#10b981"
        shadow = "rgba(16, 185, 129, 0.4)"
    elif score >= 6:
        gradient = "linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)"
        primary_color = "#f59e0b"
        shadow = "rgba(245, 158, 11, 0.4)"
    else:
        gradient = "linear-gradient(135deg, #ef4444 0%, #f87171 100%)"
        primary_color = "#ef4444"
        shadow = "rgba(239, 68, 68, 0.4)"

    bars_html = ""
    for item in sub_scores:
        val = item.get('value', 8)
        percent = int(val * 10)
        bars_html += f"""
        <div style="margin-bottom: 15px;">
            <div style="display:flex; justify-content:space-between; font-size:0.9rem; font-weight:700; margin-bottom:6px; color:#4b5563;">
                <span>{item.get('label')}</span>
                <span>{val}</span>
            </div>
            <div style="background:#f3f4f6; border-radius:99px; height:10px; width:100%; overflow:hidden;">
                <div style="width:{percent}%; height:100%; background:{gradient}; border-radius:99px;"></div>
            </div>
        </div>"""

    return f"""
    <div style='background: #ffffff; border-radius: 16px; padding: 30px; margin: 40px 0; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); border: 1px solid #f3f4f6;'>
        <div style='display: flex; flex-wrap: wrap; align-items: center; gap: 30px;'>
            <div style='flex: 0 0 auto; text-align: center; min-width: 120px; margin: 0 auto;'>
                <div style='width: 100px; height: 100px; border-radius: 50%; background: {gradient}; display: flex; align-items: center; justify-content: center; color: white; font-size: 2.5rem; font-weight: 800; box-shadow: 0 10px 15px -3px {shadow}; margin: 0 auto 15px auto;'>{score}</div>
                <div style='background: {primary_color}1a; color: {primary_color}; display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>{badge}</div>
            </div>
            <div style='flex: 1; min-width: 250px;'>
                <h3 style='margin: 0 0 20px 0; font-size: 1.5rem; color: #111827; border-bottom: 2px solid #f3f4f6; padding-bottom: 10px;'>Verdetto Finale</h3>
                {bars_html}
            </div>
        </div>
    </div>"""

def generate_faq_html(faqs):
    if not faqs: return ""
    html = '<div style="margin-top: 50px; margin-bottom: 30px;"><h2>Domande Frequenti</h2>'
    for f in faqs:
        html += f'''
<details class="rd-faq-details" style="margin-bottom: 15px; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 15px; background: #fff;">
    <summary style="font-weight: bold; cursor: pointer; color: #1f2937; outline: none;">{f.get('question')}</summary>
    <div class="rd-faq-content" style="margin-top: 10px; color: #4b5563; line-height: 1.6; border-top: 1px solid #f3f4f6; padding-top: 10px;">{f.get('answer')}</div>
</details>'''
    html += '</div>'
    return html

def analyze_price_history(product_id, current_price):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 30", (product_id,))
        rows = cursor.fetchall()
        conn.close()
        prices = [float(r[0]) for r in rows] if rows else [float(current_price)]
        current = float(current_price)
        if len(prices) > 1 and current <= min(prices): return "🔥 Minimo Storico"
        return "✅ Prezzo Ottimo" if current < (sum(prices)/len(prices)) else "⚖️ Prezzo Stabile"
    except: return "⚖️ Monitoraggio avviato"

# --- MAIN FORMATTER ---

def format_article_html(product, local_image_url, ai_data):
    p_id, asin, title, price = product[0], product[1], product[2], product[3]
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"
    p_verdict = analyze_price_history(p_id, price)
    today_str = datetime.now().strftime('%d/%m/%Y')
    
    extra_code = """
<style>
@keyframes pulse-orange { 0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0.7); } 70% { transform: scale(1.03); box-shadow: 0 0 0 10px rgba(255, 153, 0, 0); } 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0); } }
.rd-btn-pulse { animation: pulse-orange 2s infinite; }
@media (max-width: 768px) { #rd-sticky-title-id { display: none !important; } }
</style>
<script>
document.addEventListener("DOMContentLoaded", function() {
    var stickyBar = document.getElementById("rd-sticky-bar-container");
    if (stickyBar) { document.body.appendChild(stickyBar); }
    
    function checkMobile() {
        var title = document.getElementById("rd-sticky-title-id");
        if (title) {
            if (window.innerWidth < 768) { title.style.display = "none"; } 
            else { title.style.display = "block"; }
        }
    }
    window.addEventListener("resize", checkMobile);
    checkMobile();
});
</script>
"""

    badge_html = ""
    if ai_data.get('final_score', 0) >= 8.5:
        badge_html = '<div style="position: absolute; top: -10px; right: -10px; background: #ffd700; color: #000; font-weight: bold; padding: 5px 10px; border-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); font-size: 0.8rem; z-index: 10;">🏆 SCELTA TOP</div>'

    header = f"""
{extra_code}
<div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center; position: relative;">
    {badge_html}
    <div style="flex: 1; text-align: center; min-width: 200px;">
        <a href="{aff_link}" target="_blank" rel="nofollow noopener sponsored">
            <img class="lazyload" style="max-height: 250px; width: auto; object-fit: contain;" src="{clean_amazon_image_url(local_image_url)}" alt="Recensione {title}" />
        </a>
    </div>
    <div style="flex: 1.5; min-width: 250px;">
        <h2 style="margin-top: 0; font-size: 1.4rem;">{title}</h2>
        <div class="rd-price-box" style="font-size: 2.2rem; color: #b12704; font-weight: 800; margin: 10px 0;">€ {price}</div>
        <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 10px 15px; margin: 10px 0; border-radius: 4px;">
            <div style="font-weight: bold; color: #856404; text-transform: uppercase; font-size: 0.75rem;">Stato Attuale</div>
            <div class="rd-status-val" style="font-size: 0.9rem; color: #333; font-weight: 600;">{p_verdict}</div>
        </div>
        <a class="rd-btn-pulse" style="background-color: #ff9900 !important; color: #ffffff !important; padding: 14px 28px; text-decoration: none !important; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 1.1rem; margin-top: 5px;" href="{aff_link}" target="_blank" rel="nofollow noopener sponsored">
            👉 VEDI OFFERTA AMAZON
        </a>
        <p style="font-size: 0.75rem; color: #888; margin-top: 8px;">Ultimo controllo: {today_str}</p>
    </div>
</div>
"""
    
    body = ai_data.get('html_content', '')
    pros_cons = generate_pros_cons_html(ai_data.get('pros', []), ai_data.get('cons', []))
    scorecard = generate_scorecard_html(ai_data.get('final_score', 8.0), ai_data.get('verdict_badge', 'Consigliato'), ai_data.get('sub_scores', []))
    
    video = ""
    if ai_data.get('video_id'):
        video = f"<div style='margin-top:30px; border-radius:12px; overflow:hidden; box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);'><iframe width='100%' height='450' src='https://www.youtube.com/embed/{ai_data.get('video_id')}' frameborder='0' allowfullscreen></iframe></div>"

    faq = generate_faq_html(ai_data.get('faqs', []))

    # STICKY BAR with MARKERS
    sticky_bar = f"""
<div id="rd-sticky-bar-container" style="position: fixed !important; bottom: 0 !important; left: 0 !important; width: 100% !important; background: #ffffff !important; box-shadow: 0 -2px 10px rgba(0,0,0,0.1) !important; z-index: 2147483647 !important; border-top: 3px solid #ff9900 !important; padding: 0 !important;">
    <div style="max-width: 1100px !important; margin: 0 auto !important; padding: 10px 20px !important; display: flex !important; justify-content: space-between !important; align-items: center !important;">
        <div id="rd-sticky-title-id" style="font-weight:bold !important; color:#333 !important; max-width: 60% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; font-family: sans-serif !important; font-size: 1rem !important; margin: 0 !important;">{title}</div>
        <div style="display:flex !important; align-items:center !important; margin: 0 !important; margin-left: auto !important;">
            <span class="rd-sticky-price" style="font-size: 1.2rem !important; font-weight: bold !important; color: #b12704 !important; margin-right: 15px !important; white-space: nowrap !important;">€ {price}</span>
            <a href="{aff_link}" target="_blank" rel="nofollow noopener sponsored" style="background: #ff9900 !important; color: #ffffff !important; padding: 10px 20px !important; text-decoration: none !important; border-radius: 4px !important; font-weight: bold !important; text-transform: uppercase !important; font-size: 0.9rem !important; border: none !important; box-shadow: none !important; white-space: nowrap !important;">Vedi Offerta</a>
        </div>
    </div>
</div>
"""

    disclaimer = """<p style="font-size:0.7rem; color:#999; margin-top:50px; text-align:center; border-top:1px solid #eee; padding-top:15px;"><em>In qualità di Affiliato Amazon, riceviamo un guadagno dagli acquisti idonei.</em></p>"""
    
    full_html = header + body + pros_cons + scorecard + video + faq + disclaimer + sticky_bar
    
    schema_p = {
        "@context": "https://schema.org/", "@type": "Product", "name": title, "image": local_image_url,
        "description": ai_data.get('meta_description', ''),
        "offers": {"@type": "Offer", "price": str(price), "priceCurrency": "EUR", "availability": "https://schema.org/InStock"},
        "review": {"@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": str(ai_data.get('final_score', 8.0)), "bestRating": "10", "worstRating": "0"}, "author": {"@type": "Person", "name": "Redazione"}}
    }
    full_html += f'\n<script type="application/ld+json">{json.dumps(schema_p)}</script>'

    return full_html, media_id if 'media_id' in locals() else None

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
            
            full_html, _ = format_article_html(p, local_url, ai_data)
            
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
                cursor.execute("UPDATE products SET status = 'published', wp_post_id = %s WHERE id = %s", (wp_post_id, p[0]))
                cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (p[0], p[3]))
                conn.commit()
                print(f"✅ Pubblicato: {p[1]} (WP ID: {wp_post_id})")
    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    run_publisher()