import imaplib
import email
from email.header import decode_header
import requests
import os
import json
import base64
import re
import sys
import time
import shutil
import urllib.parse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURAZIONE ---
load_dotenv() 

WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER') 
WP_APP_PASSWORD = os.getenv('WP_PASSWORD') 
AMAZON_TAG = "recensionedigitale-21"

IMAP_SERVER = os.getenv('IMAP_SERVER', 'imaps.aruba.it')
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASS = os.getenv('IMAP_PASSWORD')
IMAP_FOLDER = os.getenv('IMAP_FOLDER', 'INBOX.Da Pubblicare')

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# --- FUNZIONI WP ---

def get_auth_header():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}'}

def get_all_wp_categories():
    categories = {}
    page = 1
    while True:
        try:
            url = f"{WP_API_URL}/categories?per_page=100&page={page}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200: break
            data = r.json()
            if not data: break
            for c in data: categories[c['name']] = c['id']
            page += 1
        except: break
    return categories

def extract_search_queries(body):
    prompt = f"""Leggi questo comunicato stampa e genera 3 brevi query di ricerca per trovare immagini HD su WP.
    Testo: {body[:1000]}
    Rispondi SOLO JSON: ["Query 1", "Query 2", "Query 3"]"""
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list): return result[key][:3]
            return list(result.values())[:3]
        return result[:3]
    except: return ["Tecnologia"]

def search_smart_media_on_wp(queries):
    print(f"   🔍 Ricerca elastica immagini su WP: {queries}")
    headers = get_auth_header()
    results = []
    seen_ids = set()
    for query in queries:
        if not query: continue
        safe_query = requests.utils.quote(query)
        url = f"{WP_API_URL}/media?search={safe_query}&per_page=10"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json():
                    if 'source_url' in m and 'id' in m and m['id'] not in seen_ids:
                        results.append({'id': m['id'], 'url': m['source_url']})
                        seen_ids.add(m['id'])
        except: pass
    return results

# --- ESTRAZIONE TESTO ---

def extract_text_from_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    try:
        if ext == '.pdf':
            import pypdf
            with open(filepath, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        elif ext in ['.docx', '.doc']:
            import docx
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except: pass
    return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore')

# --- LOGICA AI (GOD MODE) ---

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    cat_names = ", ".join(list(cat_list.keys()))
    
    prompt = f"""
    Sei il caporedattore tech di RecensioneDigitale.it. Scrivi una PRESENTAZIONE giornalistica PREMIUM su '{product_name}'.
    Usa la terza persona plurale e uno stile editoriale da testata tech autorevole.
    
    REGOLE FOTO (VISION):
    - Analizza FISICAMENTE le immagini fornite tramite gli URL (leggi testo, riconosci il dettaglio).
    - 'suggested_image_url': inserisci l'URL della foto che descrive MEGLIO quel paragrafo.
    - 'image_alt': descrizione tecnica di ciò che vedi.

    REGOLE EDITORIALI:
    - sections: 5 Sezioni con paragrafi da 80-120 parole. 3-5 grassetti (**) a sezione.
    - intro: DEVE avere in grassetto Brand e Prodotto.
    - faqs: ESATTAMENTE 3 domande e risposte.
    - price: Trova il prezzo nel comunicato (es. 79,99€). Se non c'è scrivi 'Vedi Prezzo'.
    - top_features: Estrai i 3 veri punti di forza del prodotto (max 10 parole l'uno).
    - specs: Estrai i dati tecnici (es. peso, risoluzione, batteria) in una lista di max 8 oggetti. 'k' è il nome (es. Autonomia), 'v' è il valore (es. 50 ore). Se non ci sono dati, lascia vuoto.
    - quote: Trova un virgolettato (citazione del CEO o PR). Compila 'text' con la frase e 'author' col nome. Altrimenti lascia vuoto.
    
    STRUTTURA JSON: seo_title, selected_cat (tra {cat_names}), meta_desc, intro, price, top_features (lista di 3 stringhe), specs (lista di oggetti k, v), quote (oggetto text, author), sections (title, content, suggested_image_url, image_alt), faqs.
    
    DATI: '{notes}'.
    """

    content_payload = [{"type": "text", "text": prompt}]
    for url in photo_urls:
        content_payload.append({"type": "text", "text": f"URL FOTO: {url}"})
        content_payload.append({"type": "image_url", "image_url": {"url": url}})
            
    response = client.chat.completions.create(
        model="gpt-4o-mini", 
        messages=[{"role": "user", "content": content_payload}], 
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- COSTRUZIONE HTML (LAYOUT PREMIUM) ---

def build_presentation_html(data, image_urls, product_name, yt_embed_code):
    price_val = data.get("price", "Vedi Prezzo")
    if price_val.strip() == "": price_val = "Vedi Prezzo"
    if "€" not in price_val and any(char.isdigit() for char in price_val): price_val = f"€ {price_val}"
    
    hero_img = image_urls[0] if image_urls else ""
    current_date = datetime.now().strftime("%d/%m/%Y")
    search_query = urllib.parse.quote(product_name)
    amazon_link = f"https://www.amazon.it/s?k={search_query}&tag={AMAZON_TAG}"
    
    btn_style = "background: linear-gradient(135deg, #ff9900 0%, #ffb84d 100%) !important; color: #ffffff !important; padding: 16px 45px !important; border-radius: 50px !important; text-decoration: none !important; font-weight: 800 !important; text-transform: uppercase !important; display: inline-block !important; font-size: 1.05rem !important; box-shadow: 0 4px 15px rgba(255, 153, 0, 0.35) !important; border: none !important; letter-spacing: 0.5px !important; line-height: normal !important;"

    head_code = """
    <style>
    .rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }
    @media (max-width: 768px) { .rd-box-responsive { padding: 15px !important; } .rd-mobile-reset { min-width: 0 !important; width: 100% !important; flex: 0 0 100% !important; max-width: 100% !important; box-sizing: border-box !important; } .rd-hero-content-col { text-align: center !important; padding-left: 0 !important; } .rd-hero-price-row { justify-content: center !important; } .rd-cta-button { padding: 14px 20px !important; width: auto !important; max-width: 100% !important; white-space: normal !important; } }
    </style>"""

    top_box = f"""
    <div class="rd-box-responsive" style="box-sizing: border-box !important; max-width: 800px; margin: 0 auto 40px auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 35px !important; display: flex; flex-wrap: wrap; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.04); gap: 40px;">
        <div class="rd-mobile-reset" style="flex: 1 1 250px; text-align: center;"><a href="{amazon_link}" target="_blank" rel="nofollow noopener sponsored"><img style="max-height: 250px; width: auto; object-fit: contain; mix-blend-mode: multiply; max-width: 100%;" src="{hero_img}" alt="{product_name}" /></a></div>
        <div class="rd-hero-content-col rd-mobile-reset" style="flex: 1 1 300px; text-align: left; padding-left: 20px;">
            <h2 style="margin-top: 0; font-size: 1.8rem; color: #1a202c; line-height: 1.25; font-weight: 800; margin-bottom: 20px;">{product_name}</h2>
            <div class="rd-hero-price-row" style="display: flex; flex-wrap: wrap; align-items: center; gap: 15px; margin-bottom: 25px;"><div style="font-size: 2.6rem; color: #b12704; font-weight: 900; letter-spacing: -1px;">{price_val}</div></div>
            <a href="{amazon_link}" target="_blank" rel="nofollow noopener sponsored" class="rd-cta-button" style="{btn_style}">Vedi Offerta su Amazon</a>
            <p style="font-size: 0.8rem; color: #94a3b8; margin-top: 15px;">Ultimo aggiornamento: {current_date}</p>
        </div>
    </div>"""

    def fmt(t):
        if not t: return ""
        f = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', t)
        return f.replace("\n- ", "<br>• ")

    # Top Features Box
    top_features_html = ""
    if data.get('top_features'):
        lis = "".join([f"<li style='margin-bottom: 10px;'>✅ <strong>{fmt(f)}</strong></li>" for f in data['top_features']])
        top_features_html = f"<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 25px; margin: 30px 0;'><h3 style='margin-top: 0; color: #0f172a; font-size: 1.3rem; margin-bottom: 15px; padding:0; border:none; background:none;'>I Punti di Forza</h3><ul style='list-style-type: none; padding-left: 0; margin: 0; color: #334155;'>{lis}</ul></div>"

    # Quote Box
    quote_html = ""
    q = data.get('quote', {})
    if q and q.get('text'):
        quote_html = f"<blockquote style='border-left: 4px solid #ff9900; margin: 40px 0; padding: 15px 25px; background: #fffaf0; font-style: italic; color: #475569; border-radius: 0 12px 12px 0;'><p style='margin: 0; font-size: 1.15rem; line-height: 1.7;'>\"{q['text']}\"</p><footer style='margin-top: 15px; font-weight: 800; color: #1e293b;'>— {q.get('author', 'Azienda')}</footer></blockquote>"

    content_html = f'<div class="rd-article-content"><p>{fmt(data.get("intro",""))}</p>{top_features_html}'
    used = []
    
    for idx, sec in enumerate(data.get('sections', [])):
        if not isinstance(sec, dict): continue
        img_url = sec.get('suggested_image_url', '').strip()
        img_tag = ""
        if img_url and img_url in image_urls and img_url not in used:
            img_tag = f'<a href="{img_url}" target="_blank"><img src="{img_url}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec.get("image_alt","")}"></a>'
            used.append(img_url)
        
        content_html += f'<h3>{fmt(sec.get("title","Info"))}</h3>{img_tag}<p>{fmt(sec.get("content",""))}</p>'
        
        # Inserimento dinamico Citazione e Video
        if idx == 0 and quote_html: content_html += quote_html
        if idx == 1 and yt_embed_code: content_html += yt_embed_code
    
    content_html += "</div>" # Chiude blocco testo principale

    # Tabella Specifiche
    if data.get('specs') and len(data['specs']) > 0:
        rows = "".join([f"<tr><td style='padding: 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #1e293b; width: 40%; background: #f8fafc;'>{s.get('k','')}</td><td style='padding: 12px; border-bottom: 1px solid #e2e8f0; color: #475569;'>{s.get('v','')}</td></tr>" for s in data['specs']])
        content_html += f"<div class='rd-article-content'><h3>Specifiche Tecniche</h3><div style='overflow-x: auto;'><table style='width: 100%; border-collapse: collapse; text-align: left; margin-bottom: 40px; font-size: 0.95rem; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.03);'><tbody>{rows}</tbody></table></div></div>"

    # Galleria HD
    remaining = [i for i in image_urls if i not in used]
    if remaining:
        gallery = "".join([f'<a href="{i}" target="_blank"><img src="{i}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);"></a>' for i in remaining])
        content_html += f"<div class='rd-article-content'><h3>Galleria Immagini</h3><div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; margin-bottom: 40px;'>{gallery}</div></div>"
    
    # FAQ
    faqs_html_list = []
    for f in data.get('faqs', []):
        if isinstance(f, dict):
            q = f.get('q', f.get('question', f.get('domanda', 'Domanda')))
            a = f.get('a', f.get('answer', f.get('risposta', '')))
            faqs_html_list.append(f"<details style='margin-bottom: 15px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px 25px; background: #ffffff;'><summary style='font-weight: 700; cursor: pointer; color: #1e293b; outline: none; font-size: 1.1rem;'>{fmt(q)}</summary><div style='margin-top: 15px; color: #475569; line-height: 1.7; border-top: 1px solid #f1f5f9; padding-top: 15px;'>{fmt(a)}</div></details>")
            
    faq_wrapper = f"<div class='rd-article-content'><h3>Domande Frequenti</h3>{''.join(faqs_html_list)}</div>" if faqs_html_list else ""
    
    schema = f"""<script type="application/ld+json">{{"@context": "https://schema.org/", "@type": "Product", "name": "{product_name}", "image": "{hero_img}", "description": "{data.get('meta_desc', '').replace('"', "'")}", "offers": {{"@type": "Offer", "price": "{price_val.replace('€', '').replace(',', '.').strip() if '€' in price_val else '0.00'}", "priceCurrency": "EUR"}}}}</script>"""
    disclaimer = "<p style='font-size: 0.75rem; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 25px; margin-top: 60px;'><em>In qualità di Affiliato Amazon, riceviamo un guadagno dagli acquisti idonei.</em></p>"

    return f"{head_code}{top_box}{content_html}{faq_wrapper}{top_box}{schema}{disclaimer}"

# --- CORE ---

def process_emails():
    print(f"\n--- 🔍 Scan {IMAP_FOLDER} (Python {sys.version.split()[0]}) ---")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        if mail.select(f'"{IMAP_FOLDER}"')[0] != "OK": return
        
        status, data = mail.search(None, 'UNSEEN')
        mail_ids = data[0].split()
        if not mail_ids: 
            mail.logout()
            return

        cat_list = get_all_wp_categories()
        temp_path = "temp_emails"
        os.makedirs(temp_path, exist_ok=True)

        for i in mail_ids:
            res, msg_data = mail.fetch(i, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            subj = u''.join(word.decode(encoding or 'utf-8') if isinstance(word, bytes) else word for word, encoding in decode_header(msg["Subject"]))
            print(f"📩 Elaborazione: {subj}")
            
            body = ""
            attachments_text = ""
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                filename = part.get_filename()
                if not filename:
                    if part.get_content_type() == "text/plain": body += part.get_payload(decode=True).decode(errors='ignore')
                else:
                    fpath = os.path.join(temp_path, filename)
                    with open(fpath, "wb") as f: f.write(part.get_payload(decode=True))
                    if os.path.splitext(filename)[1].lower() in ['.pdf', '.docx']:
                        attachments_text += f"\n--- {filename} ---\n{extract_text_from_file(fpath)}"

            # Ricerca Link YouTube (Regex)
            final_notes = f"BODY:\n{body}\n\nDOCS:\n{attachments_text}"
            yt_embed_code = ""
            yt_match = re.search(r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', final_notes)
            if yt_match:
                video_id = yt_match.group(4)
                yt_embed_code = f"<div style='position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 12px; margin: 40px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.1);'><iframe src='https://www.youtube.com/embed/{video_id}' style='position: absolute; top: 0; left: 0; width: 100%; height: 100%;' frameborder='0' allowfullscreen></iframe></div>"
                print(f"   🎥 Trovato video YouTube integrato.")

            p_name = extract_product_name(subj)
            search_queries = extract_search_queries(body)
            if p_name not in search_queries: search_queries.insert(0, p_name)
                
            wp_media_results = search_smart_media_on_wp(search_queries)
            wp_hd_urls = [m['url'] for m in wp_media_results]
            featured_id = wp_media_results[0]['id'] if wp_media_results else None
            
            ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_hd_urls)
            html = build_presentation_html(ai_data, wp_hd_urls, p_name, yt_embed_code)
            
            payload = {
                'title': ai_data.get('seo_title', p_name), 
                'content': html, 
                'excerpt': ai_data.get('meta_desc', ''), # SEO Riassunto
                'status': 'draft', 
                'categories': [cat_list.get(ai_data.get('selected_cat'), 1)],
                'slug': f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
            }
            if featured_id: payload['featured_media'] = featured_id

            r = requests.post(f"{WP_API_URL}/posts", headers=get_auth_header(), json=payload)
            if r.status_code == 201:
                print(f"   ✅ Bozza v100 creata: {r.json().get('link')}")
                mail.store(i, '+FLAGS', '\\Seen')

        shutil.rmtree(temp_path)
        mail.logout()
    except Exception as e: print(f"❌ Errore: {e}")

if __name__ == "__main__":
    print(f"🚀 Email Bot v100.0 God Mode attivo (Python {sys.version.split()[0]})")
    while True:
        process_emails()
        time.sleep(600)