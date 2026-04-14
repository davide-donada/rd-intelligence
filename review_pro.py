import requests
import os
import json
import base64
import re
import random
import time
import sys
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

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def clean_string(text):
    if not text: return ""
    return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore')

def extract_text_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"   ⚠️ Errore: Il file '{filepath}' non esiste in questa cartella.")
        return ""
    
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    print(f"   📄 Lettura del documento '{filepath}' in corso...")
    
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
        print(f"   ❌ Errore durante l'estrazione del testo: {e}")
    return clean_string(text)

def get_auth_header():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}'}

def format_text_to_html(text):
    if not text: return ""
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    formatted = formatted.replace("\n- ", "<br>• ")
    return formatted

def upload_remote_image_to_wp(image_url, title):
    print(f"   📸 Tentativo caricamento immagine: {image_url[:40]}...")
    try:
        dl_headers = {"User-Agent": random.choice(USER_AGENTS)}
        img_response = requests.get(image_url, headers=dl_headers, timeout=15)
        if img_response.status_code != 200: return None
        img_data = img_response.content
        clean_title = re.sub(r'[^a-zA-Z0-9]', '-', title).lower()[:30]
        filename = f"{clean_title}.jpg"
        headers = get_auth_header()
        headers.update({'Content-Disposition': f'attachment; filename={filename}', 'Content-Type': 'image/jpeg'})
        response = requests.post(f"{WP_API_URL}/media", headers=headers, data=img_data)
        if response.status_code == 201: return response.json().get('id')
    except: pass
    return None

def clean_amazon_image_url(url):
    if not url: return ""
    return re.sub(r'\._[A-Z0-9,_\-]+_\.', '.', url)

def get_live_amazon_details(asin):
    if not asin: return None
    url = f"https://www.amazon.it/dp/{asin}"
    session = requests.Session()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "it-IT,it;q=0.9"}
    try:
        time.sleep(random.uniform(1, 2))
        resp = session.get(url, headers=headers, timeout=20)
        if resp.status_code != 200: return {"price": "Vedi Prezzo", "image": ""}
        soup = BeautifulSoup(resp.content, "lxml")
        price = "Vedi Prezzo"
        match = re.search(r'"priceAmount":(\d+\.\d+)', resp.text)
        if match:
            price = f"€ {match.group(1).replace('.', ',')}"
        else:
            selectors = ['span.a-price.priceToPay span.a-offscreen', '#corePrice_feature_div .a-offscreen']
            for sel in selectors:
                el = soup.select_one(sel)
                if el and any(c.isdigit() for c in el.get_text()):
                    price = el.get_text(strip=True).replace(',', '.')
                    break
        img_tag = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "main-image"})
        img_url = clean_amazon_image_url(img_tag.get("src")) if img_tag else ""
        return {"price": price, "image": img_url}
    except: return {"price": "Vedi Prezzo", "image": ""}

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

def generate_review_content(product_name, notes, cat_list, photos=[], manual_score="", is_review=True):
    model_to_use = "gpt-4o-mini" 
    mode_text = "RECENSIONE COMPLETA" if is_review else "PRESENTAZIONE / NOVITÀ"
    print(f"   👁️ Generazione testo con {model_to_use} (Modalità: {mode_text} + Categorie Reali WP)...")
    
    cat_names = ", ".join(list(cat_list.keys()))
    safe_product_name = clean_string(product_name)
    safe_notes = clean_string(notes)
    
    # IMPORTANTE: Corretta la f-string per passare il nome vero del prodotto e le categorie reali al prompt.
    if is_review:
        tone_instruction = f"""
        PARLA IN TERZA PERSONA PLURALE ("Abbiamo soggiornato", "Siamo rimasti colpiti").
        Usa un tono caldo, emozionale, coinvolgente e da vero "storyteller".
        VIETATO l'uso di formule robotiche come "L'analisi ha evidenziato".
        REGOLE TITOLO: Il 'seo_title' DEVE obbligatoriamente seguire questo template: "{safe_product_name}, la recensione: [Sottotitolo]". 
        Se l'oggetto è prettamente esperienziale (es. un evento in loco o un viaggio), puoi optare per "{safe_product_name}, l'esperienza: [Sottotitolo]".
        """
        score_instruction = f"Devi assegnare ESATTAMENTE il punteggio {manual_score} come 'score_value' e giustificarlo nel testo." if manual_score else "Calcola tu un 'score_value' da 1.0 a 10.0 basandoti sull'entusiasmo degli appunti."
        json_structure = f"""
        - seo_title: "Titolo secondo il template obbligatorio"
        - selected_cat: "Scegli ESATTAMENTE uno di questi nomi (Copia e incolla): {cat_names}"
        - meta_desc: Meta description persuasiva.
        - intro: Introduzione calda e vissuta (CON GRASSETTI **).
        - sections: Lista di 5 (CINQUE) oggetti {{"title": "Titolo", "content": "Testo...", "suggested_image_url": "URL foto", "image_alt": "Breve descrizione visiva di cosa c'è nella foto per uso SEO"}}.
        - pros: Lista 3-4 pro.
        - cons: Lista 2-3 contro.
        - score_value: float.
        - score_label: stringa breve.
        - breakdown_scores: Lista 3 oggetti {{"label": "...", "val": "..."}}.
        - faqs: Lista 3 oggetti {{"q": "...", "a": "..."}}.
        - conclusion: Verdetto finale empatico.
        """
        anti_hallucination = """
        REGOLE SUI "CONTRO" (ANTI-ALLUCINAZIONE):
        - I 'contro' devono essere VERI. NON INVENTARE problemi non citati. 
        - NON inserire come difetto il fatto di non aver provato un servizio.
        """
    else:
        tone_instruction = f"""
        Questo articolo NON È UNA RECENSIONE ma una PRESENTAZIONE DI PRODOTTO O NOVITÀ (stile comunicato stampa / news).
        NON USARE MAI la prima o terza persona plurale riferita a un test ("abbiamo provato", "ci ha colpito"). Usa un tono giornalistico, accattivante, descrittivo e professionale per presentare le caratteristiche e le novità.
        REGOLE TITOLO: Il 'seo_title' DEVE essere un titolo giornalistico forte (es. "{safe_product_name}: Il nuovo capolavoro di [Brand] che rivoluziona..."). VIETATO usare la parola "recensione".
        """
        score_instruction = "NON applicabile in questo formato (ignora i voti)."
        json_structure = f"""
        - seo_title: "Titolo giornalistico/news forte"
        - selected_cat: "Scegli ESATTAMENTE uno di questi nomi (Copia e incolla): {cat_names}"
        - meta_desc: Meta description persuasiva.
        - intro: Introduzione giornalistica di presentazione (CON GRASSETTI **).
        - sections: Lista di 5 (CINQUE) oggetti {{"title": "Titolo", "content": "Testo...", "suggested_image_url": "URL foto", "image_alt": "Breve descrizione visiva di cosa c'è nella foto per uso SEO"}}.
        - faqs: Lista 3 oggetti {{"q": "...", "a": "..."}}.
        """
        anti_hallucination = ""

    prompt = f"""
    Sei il redattore appassionato e professionista di RecensioneDigitale.it. Scrivi un articolo lungo, immersivo e dettagliato su '{safe_product_name}'.
    
    {tone_instruction}
    
    FORMATTAZIONE SEO E TITOLI (CRUCIALE):
    - Paragrafi LUNGHI e corposi (almeno 80-120 parole per sezione). Fai volare l'immaginazione del lettore.
    - L'introduzione (intro) DEVE contenere almeno 3-5 grassetti (**).
    - Il campo 'content' di OGNI SINGOLA SEZIONE DEVE OBBLIGATORIAMENTE contenere dalle 3 alle 5 parole chiave in **grassetto**. Non creare MAI un paragrafo senza grassetti.
    - DIVIETO ASSOLUTO DI USARE ASTERISCHI (**) nei titoli delle sezioni, nel seo_title o nella meta description.
    
    {anti_hallucination}
    
    ABBINAMENTO FOTO E DESCRIZIONE VISIVA (ALT-TEXT AI):
    Ti passo le immagini, ognuna con il suo URL scritto testualmente sopra. Guardale.
    Nel campo 'suggested_image_url' di ogni sezione, inserisci l'URL ESATTO della foto che c'entra di più con quel paragrafo. Se nessuna foto c'entra, lascia "".
    Nel campo 'image_alt', scrivi una breve descrizione di ciò che tu AI vedi fisicamente nella foto selezionata, contestualizzandolo all'argomento del paragrafo. Questo testo sarà usato come tag alt per la SEO e l'accessibilità.
    
    VOTO:
    {score_instruction}
    
    STRUTTURA JSON CHE DEVI RESTITUIRE ESATTAMENTE:
    {json_structure}
    
    Appunti: '{safe_notes}'.
    """
    
    user_content = [{"type": "text", "text": prompt}]
    if photos:
        user_content.append({"type": "text", "text": "\nECCO LE FOTO FORNITE (Ogni foto è associata al suo URL specifico):"})
        for idx, url in enumerate(photos):
            if url.startswith("http"):
                user_content.append({"type": "text", "text": f"URL DELLA FOTO SEGUENTE: {url}"})
                user_content.append({"type": "image_url", "image_url": {"url": url}})
            
    response = client.chat.completions.create(
        model=model_to_use,
        messages=[
            {"role": "system", "content": "Sei l'Editor Senior di RecensioneDigitale.it."},
            {"role": "user", "content": user_content}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def build_magazine_html(data, user_images, details, product_name, final_link, is_amazon, is_review=True):
    if not details: details = {'price': 'Info nel testo', 'image': ''}
    price_val = details['price']
    img_val = details['image'] if details['image'] else (user_images[0] if user_images else "")
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    if is_amazon:
        btn_text = "Vedi Offerta su Amazon"
        disclaimer_text = '<em>In qualità di Affiliato Amazon, riceviamo un guadagno dagli acquisti idonei.</em>'
    else:
        btn_text = "Vedi Approfondimento" if not final_link.startswith("http") else "Vedi Offerta sul Sito"
        disclaimer_text = '<em>RecensioneDigitale.it potrebbe ricevere una commissione se ti iscrivi tramite i nostri link.</em>'
    
    intro_html = format_text_to_html(data['intro'])
    
    btn_style = "background: linear-gradient(135deg, #ff9900 0%, #ffb84d 100%) !important; color: #ffffff !important; padding: 16px 45px !important; border-radius: 50px !important; text-decoration: none !important; font-weight: 800 !important; text-transform: uppercase !important; display: inline-block !important; font-size: 1.05rem !important; box-shadow: 0 4px 15px rgba(255, 153, 0, 0.35) !important; border: none !important; letter-spacing: 0.5px !important; line-height: normal !important;"

    head_code = f"""
    <style>
    .rd-article-content h3 {{ position: relative; padding-left: 18px; border-left: 5px solid #ff9900; background: linear-gradient(90deg, #fffaf0 0%, #ffffff 100%); font-size: 1.6rem; font-weight: 800; color: #1a202c; margin-top: 50px; margin-bottom: 25px; padding-top: 10px; padding-bottom: 10px; border-radius: 0 8px 8px 0; }}
    @media (max-width: 768px) {{ .rd-box-responsive {{ padding: 15px !important; }} .rd-mobile-reset {{ min-width: 0 !important; width: 100% !important; flex: 0 0 100% !important; max-width: 100% !important; box-sizing: border-box !important; }} .rd-hero-content-col {{ text-align: center !important; padding-left: 0 !important; }} .rd-hero-price-row {{ justify-content: center !important; }} .rd-pro-con-box {{ margin-bottom: 15px !important; padding: 20px !important; }} .rd-cta-button {{ padding: 14px 20px !important; width: auto !important; max-width: 100% !important; white-space: normal !important; }} }}
    </style>"""

    hero_alt = data.get('seo_title', product_name).replace('"', "'")

    top_box = f"""
    <div class="rd-box-responsive" style="box-sizing: border-box !important; max-width: 800px; margin: 0 auto 40px auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 35px !important; display: flex; flex-wrap: wrap; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.04); gap: 40px;">
        <div class="rd-mobile-reset" style="flex: 1 1 250px; text-align: center;"><a href="{final_link}" target="_blank" rel="nofollow noopener sponsored"><img style="max-height: 250px; width: auto; object-fit: contain; mix-blend-mode: multiply; max-width: 100%;" src="{img_val}" alt="{hero_alt}" /></a></div>
        <div class="rd-hero-content-col rd-mobile-reset" style="flex: 1 1 300px; text-align: left; padding-left: 20px;">
            <h2 style="margin-top: 0; font-size: 1.8rem; color: #1a202c; line-height: 1.25; font-weight: 800; margin-bottom: 20px;">{product_name}</h2>
            <div class="rd-hero-price-row" style="display: flex; flex-wrap: wrap; align-items: center; gap: 15px; margin-bottom: 25px;"><div style="font-size: 2.6rem; color: #b12704; font-weight: 900; letter-spacing: -1px;">{price_val}</div></div>
            <a href="{final_link}" target="_blank" rel="nofollow noopener sponsored" class="rd-cta-button" style="{btn_style}">{btn_text}</a>
            <p style="font-size: 0.8rem; color: #94a3b8; margin-top: 15px;">Ultimo aggiornamento: {current_date}</p>
        </div>
    </div>"""

    content_html = f'<div class="rd-article-content"><p>{intro_html}</p>'
    
    used_images = []
    
    for idx, sec in enumerate(data.get('sections', [])):
        sec_title = sec.get('title', product_name).replace('*', '') 
        sec_content = format_text_to_html(sec.get('content', ''))
        
        sec_img = sec.get('suggested_image_url', '').strip()
        sec_alt = sec.get('image_alt', sec_title).replace('"', "'")
        
        img_tag = ""
        
        if sec_img and sec_img in user_images and sec_img not in used_images:
            img_tag = f'<a href="{sec_img}" target="_blank"><img src="{sec_img}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec_alt}"></a>'
            used_images.append(sec_img)
        else:
            for img in user_images:
                if img not in used_images:
                    img_tag = f'<a href="{img}" target="_blank"><img src="{img}" style="width: 100%; border-radius: 12px; margin: 30px 0; display: block; box-shadow: 0 4px 20px rgba(0,0,0,0.06);" alt="{sec_alt}"></a>'
                    used_images.append(img)
                    break
                    
        content_html += f'<h3>{sec_title}</h3>{img_tag}<p>{sec_content}</p>'
    
    remaining_images = [img for img in user_images if img not in used_images]
    if remaining_images:
        gallery_items = "".join([f'<a href="{img}" target="_blank"><img src="{img}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);" alt="{product_name} foto gallery"></a>' for img in remaining_images])
        content_html += f'<h3>Galleria Fotografica</h3><div style="box-sizing: border-box !important; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; margin-bottom: 40px; width: 100%;">{gallery_items}</div>'

    content_html += '</div>'

    verdict_html = ""
    schema_review_part = ""

    if is_review:
        try: score = float(data.get('score_value', 7.0))
        except: score = 7.0

        theme_grad = "linear-gradient(135deg, #10b981 0%, #34d399 100%)" if score >= 8.0 else ("linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)" if score >= 6.0 else "linear-gradient(135deg, #ef4444 0%, #f87171 100%)")
        shadow_col = "rgba(16, 185, 129, 0.4)" if score >= 8.0 else ("rgba(245, 158, 11, 0.4)" if score >= 6.0 else "rgba(239, 68, 68, 0.4)")
        bg_pill = "#ecfdf5" if score >= 8.0 else ("#fffbeb" if score >= 6.0 else "#fef2f2")
        text_pill = "#047857" if score >= 8.0 else ("#b45309" if score >= 6.0 else "#b91c1c")
        
        conclusion_html = format_text_to_html(data.get('conclusion', ''))
        pros_items = "".join([f'<li style="margin-bottom: 12px; list-style: none; padding-left: 30px; position: relative; line-height: 1.6; font-size: 1rem;"><span style="position: absolute; left: 0; top: 2px; color: #10b981; font-weight: 900; font-size: 1.2rem;">✓</span>{format_text_to_html(p)}</li>' for p in data.get('pros', [])])
        cons_items = "".join([f'<li style="margin-bottom: 12px; list-style: none; padding-left: 30px; position: relative; line-height: 1.6; font-size: 1rem;"><span style="position: absolute; left: 0; top: 2px; color: #ef4444; font-weight: 900; font-size: 1.2rem;">✕</span>{format_text_to_html(c)}</li>' for c in data.get('cons', [])])
        breakdown_html = "".join([f'<div style="margin-bottom: 20px;"><div style="display: flex; justify-content: space-between; font-size: 1rem; font-weight: 700; margin-bottom: 10px; color: #4b5563;">{item["label"]} {item["val"]}</div><div style="background: #f1f5f9; border-radius: 99px; height: 14px; width: 100%; overflow: hidden;"><div style="width: {float(item["val"])*10}%; height: 100%; background: {theme_grad}; border-radius: 99px;"></div></div></div>' for item in data.get('breakdown_scores', [])])

        verdict_html = f"""
        <div class="rd-box-responsive" style="box-sizing: border-box !important; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 40px !important; margin: 30px 0 60px 0; box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.08);">
            <div style="display: flex; flex-wrap: wrap; align-items: flex-start; gap: 40px; border-bottom: 1px solid #f1f5f9; padding-bottom: 30px; margin-bottom: 30px;">
                <div class="rd-mobile-reset" style="flex: 0 0 auto; text-align: center; min-width: 140px; margin: 0 auto;"><div style="width: 130px; height: 130px; border-radius: 50%; background: {theme_grad}; display: flex; align-items: center; justify-content: center; color: white; font-size: 3.2rem; font-weight: 800; box-shadow: 0 15px 30px -5px {shadow_col}; margin: 0 auto 20px auto;">{data.get('score_value', '')}</div><div style="background: {bg_pill}; color: {text_pill}; display: inline-block; padding: 8px 16px; border-radius: 30px; font-weight: 800; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px;">{data.get('score_label', '')}</div></div>
                <div class="rd-hero-content-col rd-mobile-reset" style="flex: 1 1 300px;"><h3 style="margin: 0 0 20px 0; font-size: 1.8rem; color: #1e293b; font-weight: 800;">Analisi Finale</h3><p style="margin-bottom: 25px; line-height: 1.8; font-size: 1.05rem; color: #475569;">{conclusion_html}</p><div>{breakdown_html}</div></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 25px; width: 100%;">
                <div class="rd-pro-con-box rd-mobile-reset" style="flex: 1 1 300px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 25px; box-sizing: border-box !important;"><h4 style="margin-top: 0; color: #166534; text-transform: uppercase; font-size: 1rem; margin-bottom: 20px; font-weight: 800; display: flex; align-items: center; gap: 8px;">👍 Cosa ci piace</h4><ul style="margin: 0; padding: 0; color: #334155;">{pros_items}</ul></div>
                <div class="rd-pro-con-box rd-mobile-reset" style="flex: 1 1 300px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 25px; box-sizing: border-box !important;"><h4 style="margin-top: 0; color: #991b1b; text-transform: uppercase; font-size: 1rem; margin-bottom: 20px; font-weight: 800; display: flex; align-items: center; gap: 8px;">👎 Cosa migliorare</h4><ul style="margin: 0; padding: 0; color: #334155;">{cons_items}</ul></div>
            </div>
        </div>
        """
        
        schema_review_part = f""", "review": {{"@type": "Review", "reviewRating": {{"@type": "Rating", "ratingValue": "{data.get('score_value', '')}", "bestRating": "10", "worstRating": "1"}}, "author": {{"@type": "Organization", "name": "RecensioneDigitale.it"}}}}"""

    faq_items = []
    for f in data.get('faqs', []):
        q_html = format_text_to_html(f.get('q'))
        a_html = format_text_to_html(f.get('a'))
        item = f"<details style='margin-bottom: 15px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px 25px; background: #ffffff;'><summary style='font-weight: 700; cursor: pointer; color: #1e293b; outline: none; font-size: 1.1rem;'>{q_html}</summary><div style='margin-top: 15px; color: #475569; line-height: 1.7; border-top: 1px solid #f1f5f9; padding-top: 15px;'>{a_html}</div></details>"
        faq_items.append(item)
    faq_html = f'<div class="rd-article-content"><h3>Domande Frequenti</h3>{"".join(faq_items)}</div>' if faq_items else ""

    schema = f"""<script type="application/ld+json">{{"@context": "https://schema.org/", "@type": "Product", "name": "{product_name}", "image": "{img_val}", "description": "{data.get('meta_desc', '').replace('"', "'")}", "offers": {{"@type": "Offer", "price": "{price_val.replace('€', '').replace(',', '.').strip() if '€' in price_val else '0.00'}", "priceCurrency": "EUR"}}{schema_review_part}}}</script>"""

    return f"{head_code}{top_box}{content_html}{verdict_html}{faq_html}{top_box}{schema}<p style='font-size: 0.75rem; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 25px; margin-top: 60px;'>{disclaimer_text}</p>"

def publish_to_wp(title, content, category_id, f_id, custom_slug):
    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'
    
    clean_title = title.replace('*', '')
    
    payload = {
        'title': clean_title, 
        'content': content, 
        'status': 'draft', 
        'categories': [category_id],
        'slug': custom_slug
    }
    
    if f_id: payload['featured_media'] = int(f_id)
    r = requests.post(f"{WP_API_URL}/posts", headers=headers, json=payload)
    if r.status_code == 201: print(f"✅ PUBBLICATO: {r.json().get('link')}")
    else: print(f"❌ ERRORE WP: {r.text}")

if __name__ == "__main__":
    print(f"🚀 RecensioneDigitale Tool v89.0 (Python {sys.version.split()[0]} - Fix Categorie Reali WP)")
    cat_list = get_all_wp_categories()
    
    print("\nScegli il formato dell'articolo:")
    print("1) Recensione Completa (Voti, Pro/Contro, Testo 'Abbiamo provato')")
    print("2) Presentazione/Novità (Stile lancio/news, NO Voti, NO Pro/Contro, Tono giornalistico)")
    tipo_art = input("Scelta (1 o 2): ").strip()
    is_review = (tipo_art != "2")

    p_name = input("\n📦 Prodotto/Servizio: ")
    
    slug_prefix = "recensione" if is_review else "presentazione"
    clean_p_name = re.sub(r'[^a-z0-9]+', '-', p_name.lower()).strip('-')
    post_slug = f"{slug_prefix}-{clean_p_name}"
    
    product_ref = input("📦 ASIN Amazon o Link Diretto: ").strip()
    
    is_amazon = False
    details = {'price': 'Info nel testo', 'image': ''}
    final_link = product_ref

    if product_ref.startswith("http"):
        is_amazon = False
        final_link = product_ref
        manual_price = input("💰 Prezzo manuale: ")
        details['price'] = manual_price
    elif product_ref:
        is_amazon = True
        final_link = f"https://www.amazon.it/dp/{product_ref}?tag={AMAZON_TAG}"
        details = get_live_amazon_details(product_ref)
    
    if not details: details = {'price': 'Info nel testo', 'image': ''}

    manual_score = ""
    if is_review:
        manual_score = input("\n⭐ Voto manuale (da 1 a 10) o premi INVIO per calcolo automatico: ").strip()

    print("\n📄 (OPZIONALE) Inserisci il nome del file PDF/Word da leggere (es. guida.pdf) o premi INVIO per saltare:")
    doc_filename = input().strip()
    testo_documento = ""
    if doc_filename:
        testo_documento = extract_text_from_file(doc_filename)
        if testo_documento:
            print(f"   ✅ Documento acquisito con successo.")

    print("\n📝 Appunti (scrivi 'FINE'):")
    notes_list = []
    while (line := input()) != "FINE": notes_list.append(line)
    
    final_notes = testo_documento + "\n\n" + "\n".join(notes_list)
    
    print("\n📸 Foto (scrivi 'FINE'):")
    photos = []
    while (line := input().strip()) != "FINE":
        if line: photos.append(line)
    
    ai_data = generate_review_content(p_name, final_notes, cat_list, photos, manual_score, is_review)
    f_media_id = upload_remote_image_to_wp(photos[0], p_name) if photos else None
    html = build_magazine_html(ai_data, photos, details, p_name, final_link, is_amazon, is_review)
    publish_to_wp(ai_data['seo_title'], html, cat_list.get(ai_data.get('selected_cat'), 1), f_media_id, post_slug)