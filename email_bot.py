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
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# --- CONFIGURAZIONE ---
load_dotenv() 

WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER') 
WP_APP_PASSWORD = os.getenv('WP_PASSWORD') 

IMAP_SERVER = os.getenv('IMAP_SERVER', 'imaps.aruba.it')
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASS = os.getenv('IMAP_PASSWORD')
IMAP_FOLDER = os.getenv('IMAP_FOLDER', 'INBOX.Da Pubblicare')

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

TEMP_DIR = "temp_pr_attachments"

def get_auth_header():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}'}

def clean_string(text):
    if not text: return ""
    return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore')

def decode_mime_words(s):
    if not s: return ""
    return u''.join(word.decode(encoding or 'utf-8') if isinstance(word, bytes) else word for word, encoding in decode_header(s))

def list_all_folders(mail):
    """Diagnostica: Stampa tutte le cartelle disponibili sul server"""
    print("\n--- DIAGNOSI CARTELLE DISPONIBILI ---")
    status, folders = mail.list()
    if status == 'OK':
        for f in folders:
            print(f" > {f.decode('utf-8')}")
    print("-------------------------------------\n")

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
        elif ext == '.txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
    except Exception as e:
        print(f"   ❌ Errore lettura {filepath}: {e}")
    return clean_string(text)

def upload_local_image_to_wp(filepath):
    """Carica un'immagine locale (allegato email) su WP e restituisce l'URL"""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    mime_type = 'image/jpeg'
    if ext == '.png': mime_type = 'image/png'
    elif ext == '.webp': mime_type = 'image/webp'
    
    try:
        with open(filepath, 'rb') as f: img_data = f.read()
        headers = get_auth_header()
        headers.update({'Content-Disposition': f'attachment; filename={filename}', 'Content-Type': mime_type})
        response = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_data)
        if response.status_code == 201: 
            return response.json().get('source_url')
    except Exception as e:
        print(f"   ❌ Errore upload {filename}: {e}")
    return None

def format_text_to_html(text):
    if not text: return ""
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    formatted = formatted.replace("\n- ", "<br>• ")
    return formatted

def is_valid_press_release(subject, body):
    """Gatekeeper AI: Controlla se l'email è davvero un comunicato stampa"""
    prompt = f"Oggetto: {subject}\nTesto: {body[:1000]}\n\nQuesto testo è un comunicato stampa o una news di presentazione prodotto adatta a un magazine tech/lifestyle? Rispondi ESATTAMENTE E SOLO 'SI' o 'NO'."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10
    )
    return "SI" in response.choices[0].message.content.upper()

def extract_product_name(subject):
    """Estrae il nome del prodotto/servizio dall'oggetto della mail"""
    prompt = f"Oggetto email: {subject}\n\nEstrai SOLO il nome del prodotto, servizio o brand principale di cui si parla. Massimo 4-5 parole. Nessun preambolo."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20
    )
    return response.choices[0].message.content.strip()

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    print(f"   🧠 Generazione articolo per '{product_name}'...")
    cat_names = ", ".join(list(cat_list.keys()))
    
    prompt = f"""
    Sei il redattore di RecensioneDigitale.it. Scrivi una PRESENTAZIONE / NOVITÀ (stile comunicato stampa o news) basata sugli appunti forniti.
    NON È UNA RECENSIONE. NON USARE MAI la prima o terza persona plurale riferita a un test ("abbiamo provato"). Usa un tono giornalistico, accattivante ed esaltante.
    
    FORMATTAZIONE E TITOLI:
    - Paragrafi LUNGHI e corposi (almeno 80-120 parole per sezione).
    - L'introduzione (intro) DEVE contenere almeno 3-5 grassetti (**).
    - Il campo 'content' di OGNI SINGOLA SEZIONE DEVE contenere dalle 3 alle 5 parole in **grassetto**.
    - DIVIETO ASSOLUTO DI USARE ASTERISCHI (**) nei titoli delle sezioni o nel seo_title.
    - REGOLE TITOLO: Il 'seo_title' DEVE essere un titolo giornalistico forte (es. "{product_name}: Il nuovo capolavoro che rivoluziona..."). VIETATO usare la parola "recensione".
    
    FOTO E ALT-TEXT:
    Nel campo 'suggested_image_url' di ogni sezione, inserisci l'URL ESATTO della foto che c'entra di più. Se nessuna c'entra, lascia "".
    Nel campo 'image_alt', scrivi una breve descrizione di ciò che tu AI vedi nella foto.
    
    STRUTTURA JSON:
    - seo_title: "Titolo giornalistico/news forte"
    - selected_cat: "Scegli ESATTAMENTE uno di questi nomi (Copia e incolla): {cat_names}"
    - meta_desc: Meta description persuasiva.
    - intro: Introduzione giornalistica (CON GRASSETTI **).
    - sections: Lista di 5 (CINQUE) oggetti {{"title": "Titolo", "content": "Testo lungo con grassetti...", "suggested_image_url": "URL foto", "image_alt": "Alt test visivo"}}.
    - faqs: Lista 3 oggetti {{"q": "...", "a": "..."}}.
    
    Appunti: '{notes}'.
    """
    
    user_content = [{"type": "text", "text": prompt}]
    if photo_urls:
        user_content.append({"type": "text", "text": "\nECCO LE FOTO FORNITE (Ogni foto è associata al suo URL):"})
        for url in photo_urls:
            user_content.append({"type": "text", "text": f"URL: {url}"})
            user_content.append({"type": "image_url", "image_url": {"url": url}})
            
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": user_content}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def build_presentation_html(data, user_images, product_name):
    intro_html = format_text_to_html(data['intro'])
    
    head_code = """<style>
    .rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }
    @media (max-width: 768px) { .rd-box-responsive { padding: 15px !important; } }
    </style>"""

    content_html = f'<div class="rd-article-content"><p>{intro_html}</p>'
    used_images = []
    
    for sec in data.get('sections', []):
        sec_title = sec.get('title', product_name).replace('*', '') 
        sec_content = format_text_to_html(sec.get('content', ''))
        sec_img = sec.get('suggested_image_url', '').strip()
        sec_alt = sec.get('image_alt', sec_title).replace('"', "'")
        
        img_tag = ""
        if sec_img and sec_img in user_images and sec_img not in used_images:
            img_tag = f'<img src="{sec_img}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec_alt}">'
            used_images.append(sec_img)
        else:
            for img in user_images:
                if img not in used_images:
                    img_tag = f'<img src="{img}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec_alt}">'
                    used_images.append(img)
                    break
        content_html += f'<h3>{sec_title}</h3>{img_tag}<p>{sec_content}</p>'
    
    remaining_images = [img for img in user_images if img not in used_images]
    if remaining_images:
        gallery_items = "".join([f'<img src="{img}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">' for img in remaining_images])
        content_html += f'<h3>Galleria Fotografica</h3><div style="box-sizing: border-box !important; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; margin-bottom: 40px; width: 100%;">{gallery_items}</div>'

    faq_items = []
    for f in data.get('faqs', []):
        q_html = format_text_to_html(f.get('q'))
        a_html = format_text_to_html(f.get('a'))
        item = f"<details style='margin-bottom: 15px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px 25px; background: #ffffff;'><summary style='font-weight: 700; cursor: pointer; color: #1e293b; outline: none; font-size: 1.1rem;'>{q_html}</summary><div style='margin-top: 15px; color: #475569; line-height: 1.7; border-top: 1px solid #f1f5f9; padding-top: 15px;'>{a_html}</div></details>"
        faq_items.append(item)
    faq_html = f'<div class="rd-article-content"><h3>Domande Frequenti</h3>{"".join(faq_items)}</div>' if faq_items else ""

    schema = f"""<script type="application/ld+json">{{"@context": "https://schema.org/", "@type": "NewsArticle", "headline": "{data.get('seo_title', '').replace('"', "'")}", "image": ["{user_images[0] if user_images else ''}"], "description": "{data.get('meta_desc', '').replace('"', "'")}"}}</script>"""

    return f"{head_code}{content_html}</div>{faq_html}{schema}"

def publish_to_wp(title, content, category_id, custom_slug):
    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'
    payload = {'title': title, 'content': content, 'status': 'draft', 'categories': [category_id], 'slug': custom_slug}
    r = requests.post(f"{WP_API_URL}/posts", headers=headers, json=payload)
    if r.status_code == 201: print(f"   ✅ BOZZA CREATA: {r.json().get('link')}")
    else: print(f"   ❌ ERRORE WP: {r.text}")

def process_emails():
    print(f"Tentativo di connessione a {IMAP_SERVER}:993...")
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        
        status, messages = mail.select(f'"{IMAP_FOLDER}"')
        if status != "OK":
            print(f"❌ Errore: Cartella '{IMAP_FOLDER}' non trovata.")
            list_all_folders(mail)
            return

        status, data = mail.search(None, 'UNSEEN')
        mail_ids = data[0].split()
        
        if not mail_ids:
            print(f"Nessuna nuova email non letta in '{IMAP_FOLDER}'.")
            mail.logout()
            return

        print(f"Trovate {len(mail_ids)} nuove email da elaborare.")
        cat_list = get_all_wp_categories()
        os.makedirs(TEMP_DIR, exist_ok=True)

        for i in mail_ids:
            try:
                print(f"\n📩 Elaborazione Email ID: {i.decode('utf-8')}")
                res, msg_data = mail.fetch(i, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                
                subject = decode_mime_words(msg["Subject"])
                print(f"   Oggetto: {subject}")
                
                body = ""
                attachments_text = ""
                local_image_paths = []

                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))

                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        try: body += part.get_payload(decode=True).decode()
                        except: pass
                    elif content_type == "text/html" and "attachment" not in content_disposition and not body:
                        try: 
                            html_body = part.get_payload(decode=True).decode()
                            body += BeautifulSoup(html_body, "html.parser").get_text()
                        except: pass
                    elif "attachment" in content_disposition:
                        filename = decode_mime_words(part.get_filename())
                        if filename:
                            filepath = os.path.join(TEMP_DIR, filename)
                            with open(filepath, "wb") as f:
                                f.write(part.get_payload(decode=True))
                            
                            ext = os.path.splitext(filename)[1].lower()
                            if ext in ['.pdf', '.docx', '.doc', '.txt']:
                                attachments_text += f"\n--- Contenuto da {filename} ---\n"
                                attachments_text += extract_text_from_file(filepath)
                            elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                local_image_paths.append(filepath)

                if not is_valid_press_release(subject, body):
                    print("   🚫 Scartata dall'AI: Non sembra un comunicato stampa valido.")
                    mail.store(i, '+FLAGS', '\\Seen')
                    continue
                
                p_name = extract_product_name(subject)
                print(f"   🏷️ Prodotto rilevato: {p_name}")

                wp_image_urls = []
                for img_path in local_image_paths:
                    wp_url = upload_local_image_to_wp(img_path)
                    if wp_url: wp_image_urls.append(wp_url)

                final_notes = f"EMAIL CORPO:\n{body}\n\nALLEGATI TESTO:\n{attachments_text}"
                ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_image_urls)
                
                html = build_presentation_html(ai_data, wp_image_urls, p_name)
                slug = f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
                
                publish_to_wp(ai_data['seo_title'], html, cat_list.get(ai_data.get('selected_cat'), 1), slug)

                mail.store(i, '+FLAGS', '\\Seen')
                print("   ✅ Operazione completata per questa email.")
                
            except Exception as e:
                print(f"   ❌ Errore durante l'elaborazione della mail {i.decode('utf-8')}: {e}")

        # Cleanup
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            
        mail.logout()

    except Exception as e:
        print(f"❌ Errore imprevisto nel server IMAP: {e}")

if __name__ == "__main__":
    print(f"🚀 Email Bot Avviato in modalità Background (Python {sys.version.split()[0]})")
    
    # Loop infinito per tenere vivo il server (Sleep di 10 minuti tra un controllo e l'altro)
    while True:
        process_emails()
        print("💤 Bot in pausa. Prossimo controllo tra 10 minuti...")
        time.sleep(600) # 600 secondi = 10 minuti