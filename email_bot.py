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
import zipfile
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

# --- FUNZIONI DI UTILITÀ ---

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

# --- ESTRAZIONE CONTENUTI ---

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
    except Exception as e:
        print(f"   ❌ Errore testo {filepath}: {e}")
    return clean_string(text)

def extract_images_from_doc(filepath):
    extracted_paths = []
    ext = os.path.splitext(filepath)[1].lower()
    base_name = os.path.basename(filepath)
    try:
        if ext == '.docx':
            with zipfile.ZipFile(filepath) as z:
                for img_info in z.infolist():
                    if img_info.filename.startswith('word/media/'):
                        img_ext = os.path.splitext(img_info.filename)[1].lower()
                        if img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            new_name = f"ext_{base_name}_{os.path.basename(img_info.filename)}"
                            dest = os.path.join(TEMP_DIR, new_name)
                            with open(dest, "wb") as f: f.write(z.read(img_info.filename))
                            extracted_paths.append(dest)
        elif ext == '.pdf':
            import fitz 
            # Silenzia i warning fastidiosi ("Ignoring wrong pointing object") dei PDF non standard
            fitz.TOOLS.mupdf_display_errors(False) 
            
            doc = fitz.open(filepath)
            for i in range(len(doc)):
                for img in doc.get_page_images(i):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3: pix = fitz.Pixmap(fitz.csRGB, pix)
                    new_name = f"ext_{base_name}_p{i}_{xref}.jpg"
                    dest = os.path.join(TEMP_DIR, new_name)
                    pix.save(dest)
                    extracted_paths.append(dest)
                    pix = None
            doc.close()
    except Exception as e:
        print(f"   ⚠️ Errore estrazione immagini da {base_name}: {e}")
    return extracted_paths

def upload_local_image_to_wp(filepath):
    if os.path.getsize(filepath) < 15000: return None 
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    mime_type = 'image/jpeg'
    if ext == '.png': mime_type = 'image/png'
    try:
        with open(filepath, 'rb') as f: img_data = f.read()
        headers = get_auth_header()
        headers.update({'Content-Disposition': f'attachment; filename={filename}', 'Content-Type': mime_type})
        response = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_data)
        if response.status_code == 201: return response.json().get('source_url')
    except: pass
    return None

# --- LOGICA AI ---

def format_text_to_html(text):
    if not text: return ""
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    formatted = formatted.replace("\n- ", "<br>• ")
    return formatted

def is_valid_press_release(subject, body):
    prompt = f"Oggetto: {subject}\ncorpo: {body[:800]}\n\nQuesto testo è un comunicato stampa o news tech/lifestyle? Rispondi SOLO 'SI' o 'NO'."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=5)
        return "SI" in response.choices[0].message.content.upper()
    except: return True

def extract_product_name(subject):
    prompt = f"Oggetto: {subject}\nEstrai il nome del prodotto/brand principale (max 4 parole). Solo il nome."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=20)
        return response.choices[0].message.content.strip()
    except: return "Nuovo Prodotto"

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    cat_names = ", ".join(list(cat_list.keys()))
    prompt = f"""
    Sei il redattore di RecensioneDigitale.it. Scrivi una PRESENTAZIONE giornalistica professionale su '{product_name}'.
    NON USARE LA PRIMA PERSONA. Parla in modo descrittivo ed esaltante (stile news).
    
    REGOLE:
    - Paragrafi lunghi (almeno 80-120 parole).
    - 3-5 grassetti (**) obbligatori per ogni paragrafo.
    - SEO Titolo: '{product_name}: [Sottotitolo accattivante]'.
    - Nel campo 'suggested_image_url' inserisci l'URL esatto della foto più pertinente guardando gli URL forniti.
    
    STRUTTURA JSON:
    - seo_title, selected_cat (una tra {cat_names}), meta_desc, intro,
    - sections (lista 5 oggetti: title, content, suggested_image_url, image_alt), faqs (lista 3 oggetti: q, a).
    
    Note: '{notes}'.
    """
    user_content = [{"type": "text", "text": prompt}]
    for url in photo_urls:
        user_content.append({"type": "text", "text": f"URL FOTO DISPONIBILE: {url}"})
        user_content.append({"type": "image_url", "image_url": {"url": url}})
            
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": user_content}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

# --- COSTRUZIONE HTML E PUBBLICAZIONE ---

def build_presentation_html(data, user_images, product_name):
    head_code = "<style>.rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }</style>"
    
    # Paracadute intro
    intro_text = data.get("intro", "")
    content_html = f'<div class="rd-article-content"><p>{format_text_to_html(intro_text)}</p>'
    used = []
    
    for sec in data.get('sections', []):
        if not isinstance(sec, dict): continue # Salta se l'AI impazzisce e non crea un dizionario
        
        # Paracadute per le chiavi del json
        sec_title = sec.get("title", "Caratteristiche")
        sec_content = sec.get("content", "")
        img_url = sec.get('suggested_image_url', '').strip()
        img_alt = sec.get("image_alt", sec_title).replace('"', "'")
        
        img_tag = ""
        if img_url and img_url in user_images and img_url not in used:
            img_tag = f'<img src="{img_url}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{img_alt}">'
            used.append(img_url)
        content_html += f'<h3>{sec_title}</h3>{img_tag}<p>{format_text_to_html(sec_content)}</p>'
    
    remaining = [i for i in user_images if i not in used]
    if remaining:
        gallery = "".join([f'<img src="{i}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">' for i in remaining])
        content_html += f'<h3>Galleria Immagini</h3><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; margin-bottom: 40px;">{gallery}</div>'
    
    # Paracadute per le FAQ (Gestione dell'errore 'q')
    faqs_html_list = []
    for f in data.get('faqs', []):
        if isinstance(f, dict):
            # Se manca 'q' o 'a', usa stringhe vuote invece di andare in errore
            q_text = f.get('q', f.get('question', f.get('domanda', 'Domanda')))
            a_text = f.get('a', f.get('answer', f.get('risposta', '')) )
            
            faqs_html_list.append(f"<details style='margin-bottom: 15px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px 25px; background: #ffffff;'><summary style='font-weight: 700; cursor: pointer; color: #1e293b; outline: none; font-size: 1.1rem;'>{q_text}</summary><div style='margin-top: 15px; color: #475569; line-height: 1.7; border-top: 1px solid #f1f5f9; padding-top: 15px;'>{a_text}</div></details>")
            
    faqs = "".join(faqs_html_list)
    faq_wrapper = f'<div class="rd-article-content"><h3>Domande Frequenti</h3>{faqs}</div>' if faqs else ""
    
    return f"{head_code}{content_html}</div>{faq_wrapper}"

def process_emails():
    print(f"\n--- 🔍 Controllo email in {IMAP_FOLDER} ---")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        if mail.select(f'"{IMAP_FOLDER}"')[0] != "OK":
            print(f"❌ Cartella {IMAP_FOLDER} non accessibile.")
            mail.logout()
            return
        
        status, data = mail.search(None, 'UNSEEN')
        mail_ids = data[0].split()
        if not mail_ids:
            print("Nessuna nuova email non letta.")
            mail.logout()
            return

        print(f"Trovate {len(mail_ids)} email da elaborare.")
        cat_list = get_all_wp_categories()
        os.makedirs(TEMP_DIR, exist_ok=True)

        for i in mail_ids:
            try:
                res, msg_data = mail.fetch(i, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                subject = decode_mime_words(msg["Subject"])
                print(f"📩 Elaborazione: {subject}")
                
                body = ""
                attachments_text = ""
                local_image_paths = []

                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = decode_mime_words(part.get_filename()) if part.get_filename() else None
                    
                    if not filename:
                        if part.get_content_type() == "text/plain": body += part.get_payload(decode=True).decode(errors='ignore')
                    else:
                        filepath = os.path.join(TEMP_DIR, filename)
                        with open(filepath, "wb") as f: f.write(part.get_payload(decode=True))
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in ['.pdf', '.docx']:
                            attachments_text += f"\n--- {filename} ---\n{extract_text_from_file(filepath)}"
                            local_image_paths.extend(extract_images_from_doc(filepath))
                        elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            local_image_paths.append(filepath)

                if not is_valid_press_release(subject, body):
                    print("   🚫 Email scartata: non sembra un comunicato stampa.")
                    mail.store(i, '+FLAGS', '\\Seen')
                    continue
                
                p_name = extract_product_name(subject)
                wp_image_urls = []
                for path in list(set(local_image_paths)):
                    url = upload_local_image_to_wp(path)
                    if url: wp_image_urls.append(url)

                final_notes = f"BODY:\n{body}\n\nATTACHMENTS:\n{attachments_text}"
                ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_image_urls)
                html = build_presentation_html(ai_data, wp_image_urls, p_name)
                
                # Paracadute per il SEO Title (se mancante)
                seo_title = ai_data.get('seo_title', f"{p_name}: La nostra presentazione")
                
                slug = f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
                payload = {
                    'title': seo_title, 
                    'content': html, 
                    'status': 'draft', 
                    'categories': [cat_list.get(ai_data.get('selected_cat'), 1)], 
                    'slug': slug
                }
                headers = get_auth_header()
                headers['Content-Type'] = 'application/json'
                r = requests.post(f"{WP_API_URL}/posts", headers=headers, json=payload)
                
                if r.status_code == 201:
                    print(f"   ✅ Bozza creata: {r.json().get('link')}")
                    mail.store(i, '+FLAGS', '\\Seen')
                else:
                    print(f"   ❌ Errore pubblicazione WP: {r.text}")

            except Exception as e:
                print(f"   ❌ Errore durante l'elaborazione della mail: {e}")

        if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
        mail.logout()
    except Exception as e:
        print(f"❌ Errore connessione IMAP: {e}")

if __name__ == "__main__":
    print(f"🚀 Email Bot v93.0 attivo (Python {sys.version.split()[0]})")
    while True:
        process_emails()
        print("💤 In attesa 10 minuti per il prossimo controllo...")
        time.sleep(600)