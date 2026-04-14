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
    """Estrae immagini incorporate in PDF o DOCX e restituisce i percorsi locali"""
    extracted_paths = []
    ext = os.path.splitext(filepath)[1].lower()
    base_name = os.path.basename(filepath)
    
    try:
        if ext == '.docx':
            # Un file .docx è uno zip. Le foto sono in word/media/
            with zipfile.ZipFile(filepath) as z:
                for img_info in z.infolist():
                    if img_info.filename.startswith('word/media/'):
                        img_ext = os.path.splitext(img_info.filename)[1].lower()
                        if img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            new_name = f"extracted_{base_name}_{os.path.basename(img_info.filename)}"
                            dest = os.path.join(TEMP_DIR, new_name)
                            with open(dest, "wb") as f:
                                f.write(z.read(img_info.filename))
                            extracted_paths.append(dest)
                            
        elif ext == '.pdf':
            # Usa PyMuPDF (fitz) per estrarre immagini da PDF
            import fitz 
            doc = fitz.open(filepath)
            for i in range(len(doc)):
                for img in doc.get_page_images(i):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3: pix = fitz.Pixmap(fitz.csRGB, pix)
                    new_name = f"extracted_{base_name}_p{i}_{xref}.jpg"
                    dest = os.path.join(TEMP_DIR, new_name)
                    pix.save(dest)
                    extracted_paths.append(dest)
                    pix = None
            doc.close()
    except Exception as e:
        print(f"   ⚠️ Impossibile estrarre immagini da {base_name}: {e}")
        
    return extracted_paths

def upload_local_image_to_wp(filepath):
    filename = os.path.basename(filepath)
    # Evitiamo file troppo piccoli (icone, loghi minuscoli)
    if os.path.getsize(filepath) < 15000: return None 
    
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

def format_text_to_html(text):
    if not text: return ""
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    formatted = formatted.replace("\n- ", "<br>• ")
    return formatted

def is_valid_press_release(subject, body):
    prompt = f"Oggetto: {subject}\nTesto: {body[:1000]}\n\nQuesto testo è un comunicato stampa o una news di presentazione prodotto? Rispondi SOLO 'SI' o 'NO'."
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=10)
    return "SI" in response.choices[0].message.content.upper()

def extract_product_name(subject):
    prompt = f"Oggetto email: {subject}\n\nEstrai SOLO il nome del prodotto/brand principale (max 4 parole)."
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=20)
    return response.choices[0].message.content.strip()

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    cat_names = ", ".join(list(cat_list.keys()))
    prompt = f"""
    Sei il redattore di RecensioneDigitale.it. Scrivi una PRESENTAZIONE giornalistica su '{product_name}'.
    NON USARE LA PRIMA PERSONA. Tono professionale da news tecnologica.
    
    REGOLE:
    - Paragrafi lunghi e ricchi (80-120 parole).
    - 3-5 grassetti (**) per sezione obbligatori.
    - SEO Titolo: '{product_name}: [Sottotitolo]'.
    - Associa le foto (suggested_image_url) in base al contenuto del paragrafo guardando gli URL forniti.
    
    STRUTTURA JSON:
    - seo_title, selected_cat (una tra {cat_names}), meta_desc, intro,
    - sections (lista 5 oggetti: title, content, suggested_image_url, image_alt), faqs.
    
    Dati: '{notes}'.
    """
    user_content = [{"type": "text", "text": prompt}]
    for url in photo_urls:
        user_content.append({"type": "text", "text": f"FOTO: {url}"})
        user_content.append({"type": "image_url", "image_url": {"url": url}})
            
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": user_content}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def build_presentation_html(data, user_images, product_name):
    head_code = "<style>.rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }</style>"
    content_html = f'<div class="rd-article-content"><p>{format_text_to_html(data["intro"])}</p>'
    used = []
    for sec in data.get('sections', []):
        img_url = sec.get('suggested_image_url', '').strip()
        img_tag = ""
        if img_url and img_url in user_images and img_url not in used:
            img_tag = f'<img src="{img_url}" style="width: 100%; border-radius: 12px; margin: 30px 0;" alt="{sec.get("image_alt", "")}">'
            used.append(img_url)
        content_html += f'<h3>{sec["title"]}</h3>{img_tag}<p>{format_text_to_html(sec["content"])}</p>'
    
    remaining = [i for i in user_images if i not in used]
    if remaining:
        gallery = "".join([f'<img src="{i}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px;">' for i in remaining])
        content_html += f'<h3>Galleria Immagini</h3><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">{gallery}</div>'
    
    faqs = "".join([f"<details style='border: 1px solid #eee; padding: 15px; margin-bottom: 10px;'><summary style='font-weight: 800;'>{f['q']}</summary>{f['a']}</details>" for f in data.get('faqs', [])])
    return f"{head_code}{content_html}</div>{faqs}"

def process_emails():
    print(f"🚀 Email Bot v91.0 attivo (Python {sys.version.split()[0]})")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        if mail.select(f'"{IMAP_FOLDER}"')[0] != "OK": return
        
        mail_ids = mail.search(None, 'UNSEEN')[1][0].split()
        if not mail_ids: return

        cat_list = get_all_wp_categories()
        os.makedirs(TEMP_DIR, exist_ok=True)

        for i in mail_ids:
            msg = email.message_from_bytes(mail.fetch(i, '(RFC822)')[1][0][1])
            subject = decode_mime_words(msg["Subject"])
            print(f"📩 In lavorazione: {subject}")
            
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
                        # COLLABORAZIONE: Estraiamo anche le foto dal documento!
                        local_image_paths.extend(extract_images_from_doc(filepath))
                    elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        local_image_paths.append(filepath)

            if not is_valid_press_release(subject, body):
                mail.store(i, '+FLAGS', '\\Seen')
                continue
            
            p_name = extract_product_name(subject)
            wp_image_urls = []
            for path in list(set(local_image_paths)): # Rimuove duplicati
                url = upload_local_image_to_wp(path)
                if url: wp_image_urls.append(url)

            final_notes = f"EMAIL:\n{body}\n\nALLEGATI:\n{attachments_text}"
            ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_image_urls)
            html = build_presentation_html(ai_data, wp_image_urls, p_name)
            
            # Pubblica Bozza
            headers = get_auth_header()
            headers['Content-Type'] = 'application/json'
            slug = f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
            payload = {'title': ai_data['seo_title'], 'content': html, 'status': 'draft', 'categories': [cat_list.get(ai_data.get('selected_cat'), 1)], 'slug': slug}
            requests.post(f"{WP_API_URL}/posts", headers=headers, json=payload)

            mail.store(i, '+FLAGS', '\\Seen')
            print(f"   ✅ Bozza creata per {p_name}")

        shutil.rmtree(TEMP_DIR)
        mail.logout()
    except Exception as e: print(f"❌ Errore: {e}")

if __name__ == "__main__":
    while True:
        process_emails()
        print("💤 In attesa 10 min...")
        time.sleep(600)