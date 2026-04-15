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
    prompt = f"""Leggi questo comunicato stampa e genera 3 brevi query di ricerca (max 3 parole l'una) per trovare immagini adatte nel database del sito.
    1. Il nome esatto del prodotto/modello.
    2. Il nome del brand + la categoria.
    3. Il contesto d'uso o parola chiave.
    Rispondi SOLO con un array JSON di stringhe. Esempio: ["GXT 499W Forta", "Trust cuffie", "Gaming PS5"]
    Testo: {body[:1000]}"""
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list): return result[key][:3]
            return list(result.values())[:3]
        return result[:3]
    except Exception as e: return ["Tecnologia"]

def search_smart_media_on_wp(queries):
    print(f"   🔍 Avvio ricerca elastica immagini su WP: {queries}")
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

# --- ESTRAZIONE TESTO E LOGICA AI ---

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

def is_valid_press_release(subject, body):
    prompt = f"Oggetto: {subject}\ncorpo: {body[:800]}\n\nQuesto testo è un comunicato stampa o news tech? Rispondi SOLO 'SI' o 'NO'."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=5)
        return "SI" in response.choices[0].message.content.upper()
    except: return True

def extract_product_name(subject):
    prompt = f"Oggetto: {subject}\nEstrai il nome del prodotto/brand principale (max 3 parole). Solo il nome."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=20)
        return response.choices[0].message.content.strip()
    except: return "Nuovo Prodotto"

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    cat_names = ", ".join(list(cat_list.keys()))
    prompt = f"""
    Sei il redattore di RecensioneDigitale.it. Scrivi una PRESENTAZIONE giornalistica professionale su '{product_name}'.
    
    REGOLE CRUCIALI:
    - Paragrafi corposi (80-120 parole).
    - SEO Titolo: '{product_name}: [Sottotitolo accattivante]'.
    - Nel campo 'suggested_image_url' inserisci l'URL esatto della foto più pertinente (se nessuna è adatta lascia "").
    - faqs: Genera ESATTAMENTE 3 domande e risposte. Non una di più, non una di meno.
    - price: Trova il prezzo nel comunicato. Se non c'è scrivi 'Vedi Prezzo'.
    
    REGOLE GRASSETTI (**):
    1. Il campo 'intro' DEVE obbligatoriamente contenere il nome del Brand e del Prodotto in **grassetto**, più un'altra parola chiave.
    2. Ogni oggetto dentro 'sections' DEVE obbligatoriamente avere dalle 3 alle 5 parole in **grassetto** nel campo 'content'.
    
    STRUTTURA JSON: seo_title, selected_cat (tra {cat_names}), meta_desc, intro, price, sections (lista 5 oggetti: title, content, suggested_image_url, image_alt), faqs (lista 3 oggetti: q, a).
    
    Note: '{notes}'.
    """
    user_content = [{"type": "text", "text": prompt}]
    for url in photo_urls:
        user_content.append({"type": "text", "text": f"URL FOTO: {url}"})
            
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": user_content}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

# --- COSTRUZIONE HTML (LAYOUT COMPLETO) ---

def build_presentation_html(data, image_urls, product_name):
    # Dati per i box
    price_val = data.get("price", "Vedi Prezzo")
    if price_val.strip() == "": price_val = "Vedi Prezzo"
    if "€" not in price_val and any(char.isdigit() for char in price_val): price_val = f"€ {price_val}"
    
    hero_img = image_urls[0] if image_urls else ""
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    # Generazione Smart Link Amazon
    search_query = urllib.parse.quote(product_name)
    amazon_link = f"https://www.amazon.it/s?k={search_query}&tag={AMAZON_TAG}"
    
    btn_style = "background: linear-gradient(135deg, #ff9900 0%, #ffb84d 100%) !important; color: #ffffff !important; padding: 16px 45px !important; border-radius: 50px !important; text-decoration: none !important; font-weight: 800 !important; text-transform: uppercase !important; display: inline-block !important; font-size: 1.05rem !important; box-shadow: 0 4px 15px rgba(255, 153, 0, 0.35) !important; border: none !important; letter-spacing: 0.5px !important; line-height: normal !important;"

    head_code = """
    <style>
    .rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }
    @media (max-width: 768px) { .rd-box-responsive { padding: 15px !important; } .rd-mobile-reset { min-width: 0 !important; width: 100% !important; flex: 0 0 100% !important; max-width: 100% !important; box-sizing: border-box !important; } .rd-hero-content-col { text-align: center !important; padding-left: 0 !important; } .rd-hero-price-row { justify-content: center !important; } .rd-pro-con-box { margin-bottom: 15px !important; padding: 20px !important; } .rd-cta-button { padding: 14px 20px !important; width: auto !important; max-width: 100% !important; white-space: normal !important; } }
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

    content_html = f'<div class="rd-article-content"><p>{fmt(data.get("intro",""))}</p>'
    used = []
    
    for sec in data.get('sections', []):
        if not isinstance(sec, dict): continue
        img_url = sec.get('suggested_image_url', '').strip()
        img_tag = ""
        if img_url and img_url in image_urls and img_url not in used:
            img_tag = f'<img src="{img_url}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec.get("image_alt","")}">'
            used.append(img_url)
        content_html += f'<h3>{sec.get("title","Info")}</h3>{img_tag}<p>{fmt(sec.get("content",""))}</p>'
    
    remaining = [i for i in image_urls if i not in used]
    if remaining:
        # Galleria immagini ora cliccabili in alta definizione
        gallery = "".join([f'<a href="{i}" target="_blank"><img src="{i}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);"></a>' for i in remaining])
        content_html += f'<h3>Galleria Immagini</h3><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; margin-bottom: 40px;">{gallery}</div>'
    
    content_html += "</div>"

    faqs_html_list = []
    for f in data.get('faqs', []):
        if isinstance(f, dict):
            q = f.get('q', f.get('question', f.get('domanda', 'Domanda')))
            a = f.get('a', f.get('answer', f.get('risposta', '')))
            faqs_html_list.append(f"<details style='margin-bottom: 15px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px 25px; background: #ffffff;'><summary style='font-weight: 700; cursor: pointer; color: #1e293b; outline: none; font-size: 1.1rem;'>{q}</summary><div style='margin-top: 15px; color: #475569; line-height: 1.7; border-top: 1px solid #f1f5f9; padding-top: 15px;'>{a}</div></details>")
            
    faq_wrapper = f"<div class='rd-article-content'><h3>Domande Frequenti</h3>{''.join(faqs_html_list)}</div>" if faqs_html_list else ""
    
    schema = f"""<script type="application/ld+json">{{"@context": "https://schema.org/", "@type": "Product", "name": "{product_name}", "image": "{hero_img}", "description": "{data.get('meta_desc', '').replace('"', "'")}", "offers": {{"@type": "Offer", "price": "{price_val.replace('€', '').replace(',', '.').strip() if '€' in price_val else '0.00'}", "priceCurrency": "EUR"}}}}</script>"""
    disclaimer = "<p style='font-size: 0.75rem; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 25px; margin-top: 60px;'><em>In qualità di Affiliato Amazon, riceviamo un guadagno dagli acquisti idonei.</em></p>"

    return f"{head_code}{top_box}{content_html}{faq_wrapper}{top_box}{schema}{disclaimer}"

# --- CORE ---

def process_emails():
    print(f"\n--- 🔍 Scan {IMAP_FOLDER} ---")
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

            if not is_valid_press_release(subj, body):
                mail.store(i, '+FLAGS', '\\Seen')
                continue
            
            p_name = extract_product_name(subj)
            search_queries = extract_search_queries(body)
            
            if p_name not in search_queries: search_queries.insert(0, p_name)
                
            wp_media_results = search_smart_media_on_wp(search_queries)
            wp_hd_urls = [m['url'] for m in wp_media_results]
            featured_id = wp_media_results[0]['id'] if wp_media_results else None
            
            final_notes = f"BODY:\n{body}\n\nDOCS:\n{attachments_text}"
            ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_hd_urls)
            html = build_presentation_html(ai_data, wp_hd_urls, p_name)
            
            payload = {
                'title': ai_data.get('seo_title', p_name), 
                'content': html, 
                'status': 'draft', 
                'categories': [cat_list.get(ai_data.get('selected_cat'), 1)],
                'slug': f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
            }
            if featured_id:
                payload['featured_media'] = featured_id

            r = requests.post(f"{WP_API_URL}/posts", headers=get_auth_header(), json=payload)
            if r.status_code == 201:
                print(f"   ✅ Bozza HD Completa creata: {r.json().get('link')}")
                mail.store(i, '+FLAGS', '\\Seen')

        shutil.rmtree(temp_path)
        mail.logout()
    except Exception as e: print(f"❌ Errore: {e}")

if __name__ == "__main__":
    print(f"🚀 Email Bot v98.0 Full Layout attivo (Python {sys.version.split()[0]})")
    while True:
        process_emails()
        time.sleep(600)