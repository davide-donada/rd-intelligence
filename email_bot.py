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
    """L'AI genera 3 query di ricerca ottimali in base al testo dell'email"""
    prompt = f"""Leggi questo comunicato stampa e genera 3 brevi query di ricerca (max 3 parole l'una) per trovare immagini adatte nel database del sito.
    1. Il nome esatto del prodotto/modello.
    2. Il nome del brand + la categoria (es. "Trust cuffie").
    3. Il contesto d'uso o la parola chiave principale (es. "Gaming PS5").
    
    Rispondi SOLO con un array JSON di stringhe. Esempio: ["GXT 499W Forta", "Trust cuffie", "Gaming PS5"]
    
    Testo: {body[:1000]}"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}], 
            response_format={"type": "json_object"} # Costringiamo una risposta JSON per sicurezza
        )
        # Gestiamo il caso in cui l'AI restituisca un dict invece di una lista pura
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict):
            # Cerca la prima lista all'interno del dizionario
            for key in result:
                if isinstance(result[key], list): return result[key][:3]
            return list(result.values())[:3]
        return result[:3]
    except Exception as e: 
        print(f"   ⚠️ Errore AI Search Queries: {e}")
        return ["Tecnologia"] # Fallback

def search_smart_media_on_wp(queries):
    """Esegue una ricerca a cascata su WP usando le query generate dall'AI"""
    print(f"   🔍 Avvio ricerca elastica immagini su WP con query: {queries}")
    headers = get_auth_header()
    results = []
    seen_ids = set()
    
    for query in queries:
        if not query: continue
        print(f"      > Cerco: '{query}'...")
        # urlencode manuale per sicurezza
        safe_query = requests.utils.quote(query)
        url = f"{WP_API_URL}/media?search={safe_query}&per_page=10"
        
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                media_list = r.json()
                found_count = 0
                for m in media_list:
                    if 'source_url' in m and 'id' in m and m['id'] not in seen_ids:
                        results.append({'id': m['id'], 'url': m['source_url']})
                        seen_ids.add(m['id'])
                        found_count += 1
                print(f"        Trovate {found_count} nuove immagini.")
        except Exception as e:
            print(f"        ⚠️ Timeout o errore ricerca: {e}")
            
    print(f"   🖼️ Ricerca completata. Totale immagini uniche trovate: {len(results)}")
    return results

# --- ESTRAZIONE TESTO E LOGICA AI DI BASE ---

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
    return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore')

def is_valid_press_release(subject, body):
    prompt = f"Oggetto: {subject}\ncorpo: {body[:800]}\n\nQuesto testo è un comunicato stampa o news tech/lifestyle? Rispondi SOLO 'SI' o 'NO'."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=5)
        return "SI" in response.choices[0].message.content.upper()
    except: return True

def extract_product_name(subject):
    """Usiamo ancora questo solo per il SEO Title e lo slug"""
    prompt = f"Oggetto: {subject}\nEstrai il nome del prodotto/brand principale (max 3 parole). Solo il nome."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=20)
        return response.choices[0].message.content.strip()
    except: return "Nuovo Prodotto"

def generate_presentation_content(product_name, notes, cat_list, photo_urls):
    cat_names = ", ".join(list(cat_list.keys()))
    prompt = f"""
    Sei il redattore di RecensioneDigitale.it. Scrivi una PRESENTAZIONE giornalistica professionale su '{product_name}'.
    REGOLE: Paragrafi lunghi (80-120 parole), 3-5 grassetti (**) obbligatori, SEO Titolo accattivante.
    Nel campo 'suggested_image_url' inserisci l'URL esatto della foto più pertinente guardando attentamente gli URL forniti e deducendone il contenuto dal nome del file. Se nessuna sembra pertinente, lascia vuoto "".
    
    STRUTTURA JSON: seo_title, selected_cat (una tra {cat_names}), meta_desc, intro, sections (lista 5 oggetti: title, content, suggested_image_url, image_alt), faqs.
    
    Note: '{notes}'.
    """
    user_content = [{"type": "text", "text": prompt}]
    for url in photo_urls:
        user_content.append({"type": "text", "text": f"URL FOTO DISPONIBILE: {url}"})
        # Opzionale: de-commenta la riga sotto se vuoi che l'AI "guardi" fisicamente le foto (consuma più token)
        # user_content.append({"type": "image_url", "image_url": {"url": url}}) 
            
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": user_content}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

# --- COSTRUZIONE HTML ---

def build_presentation_html(data, image_urls):
    head_code = "<style>.rd-article-content h3 { position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }</style>"
    
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
            img_tag = f'<img src="{img_url}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block;" alt="{sec.get("image_alt","")}">'
            used.append(img_url)
        content_html += f'<h3>{sec.get("title","Info")}</h3>{img_tag}<p>{fmt(sec.get("content",""))}</p>'
    
    remaining = [i for i in image_urls if i not in used]
    if remaining:
        gallery = "".join([f'<img src="{i}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px;">' for i in remaining])
        content_html += f'<h3>Galleria Immagini HD</h3><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px;">{gallery}</div>'
    
    faqs_html_list = []
    for f in data.get('faqs', []):
        if isinstance(f, dict):
            q = f.get('q', f.get('question', f.get('domanda', 'Domanda')))
            a = f.get('a', f.get('answer', f.get('risposta', '')))
            faqs_html_list.append(f"<details style='margin-bottom: 10px; border: 1px solid #eee; padding: 15px;'><summary style='font-weight: 700; cursor: pointer;'>{q}</summary>{a}</details>")
            
    faq_wrapper = f"<div class='rd-article-content'><h3>FAQ</h3>{''.join(faqs_html_list)}</div>" if faqs_html_list else ""
    return f"{head_code}{content_html}</div>{faq_wrapper}"

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
            
            # --- ESTRAZIONE NOME PRODOTTO E QUERY MULTIPLE ---
            p_name = extract_product_name(subj)
            search_queries = extract_search_queries(body)
            
            # --- RICERCA SMART MEDIA SU WP ---
            # Se l'AI non ha incluso il p_name nelle query, forziamolo all'inizio della lista
            if p_name not in search_queries:
                search_queries.insert(0, p_name)
                
            wp_media_results = search_smart_media_on_wp(search_queries)
            wp_hd_urls = [m['url'] for m in wp_media_results]
            
            # Prendiamo il primo ID trovato per l'Immagine in Evidenza (se esiste)
            featured_id = wp_media_results[0]['id'] if wp_media_results else None
            
            final_notes = f"BODY:\n{body}\n\nDOCS:\n{attachments_text}"
            ai_data = generate_presentation_content(p_name, final_notes, cat_list, wp_hd_urls)
            html = build_presentation_html(ai_data, wp_hd_urls)
            
            payload = {
                'title': ai_data.get('seo_title', p_name), 
                'content': html, 
                'status': 'draft', 
                'categories': [cat_list.get(ai_data.get('selected_cat'), 1)],
                'slug': f"presentazione-{re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')}"
            }
            if featured_id:
                payload['featured_media'] = featured_id
                print(f"   📌 Immagine in evidenza impostata (ID: {featured_id})")

            r = requests.post(f"{WP_API_URL}/posts", headers=get_auth_header(), json=payload)
            if r.status_code == 201:
                print(f"   ✅ Bozza HD creata: {r.json().get('link')}")
                mail.store(i, '+FLAGS', '\\Seen')

        shutil.rmtree(temp_path)
        mail.logout()
    except Exception as e: print(f"❌ Errore: {e}")

if __name__ == "__main__":
    print(f"🚀 Email Bot v96.0 Smart Search attivo (Python {sys.version.split()[0]})")
    while True:
        process_emails()
        time.sleep(600)