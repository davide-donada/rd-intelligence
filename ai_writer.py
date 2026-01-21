import os
import json
import requests
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Fallback in caso il sito sia irraggiungibile
DEFAULT_MAP = {
    'Tecnologia': 1, 'Smartphone': 60, 'Informatica': 3454, 'Elettrodomestici': 3612
}

def get_live_categories():
    """
    Scarica le categorie reali dal sito WordPress per avere ID sempre corretti.
    """
    url = "https://www.recensionedigitale.it/wp-json/wp/v2/categories?per_page=100&hide_empty=false"
    print("   🌍 Aggiornamento lista categorie da WordPress...")
    try:
        # Timeout breve per non bloccare tutto se il sito è lento
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            cats = resp.json()
            # Crea dizionario { 'Nome Categoria': ID }
            live_map = {c['name']: c['id'] for c in cats}
            print(f"   ✅ Mappate {len(live_map)} categorie dal sito.")
            return live_map
        else:
            print(f"   ⚠️ API WP errore {resp.status_code}, uso fallback.")
    except Exception as e:
        print(f"   ⚠️ Errore fetch categorie: {e}")
    
    return DEFAULT_MAP

# Carichiamo la mappa UNA VOLTA all'avvio dello script (o del worker)
CATEGORIES_MAP = get_live_categories()

def genera_recensione_seo(product_data):
    title = product_data.get('title', 'Prodotto')
    price = product_data.get('price', 0)
    
    # Prepariamo la lista per il prompt
    cat_list_str = ", ".join(CATEGORIES_MAP.keys())

    prompt_system = f"""
    Sei il Capo Redattore di RecensioneDigitale.it.
    
    COMPITO:
    Scrivi una recensione HTML professionale (h2, h3, p, ul).
    Scegli la categoria PIÙ ADATTA per questo prodotto ESCLUSIVAMENTE dalla lista sotto.
    
    LISTA CATEGORIE VALIDE (Usa uno di questi nomi esatti):
    [{cat_list_str}]
    
    REGOLE:
    1. HTML puro (no markdown).
    2. Terza persona plurale.
    3. Niente voti nel testo.
    
    JSON RICHIESTO:
    {{
        "html_content": "...",
        "meta_description": "...",
        "category_name": "Nome esatto della categoria scelta",
        "pros": ["Pro 1", "Pro 2"],
        "cons": ["Contro 1", "Contro 2"],
        "sub_scores": [
            {{ "label": "Qualità", "value": 8.0 }},
            {{ "label": "Prezzo", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": f"Titolo: {title}. Prezzo: {price}"}
            ],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        
        # --- LOGICA DI ASSEGNAZIONE ID BLINDATA ---
        chosen_name = data.get('category_name', '')
        
        # 1. Cerca corrispondenza esatta
        final_id = CATEGORIES_MAP.get(chosen_name)
        
        # 2. Se non trova esatta, cerca parziale (case insensitive)
        if not final_id:
            for key, val in CATEGORIES_MAP.items():
                if chosen_name.lower() in key.lower() or key.lower() in chosen_name.lower():
                    final_id = val
                    # Aggiorniamo il nome nel JSON per coerenza
                    data['category_name'] = key 
                    break
        
        # 3. Fallback finale su "Tecnologia" (ID 1)
        data['category_id'] = final_id if final_id else 1
        
        # Calcolo Media Voti
        voti = [s['value'] for s in data.get('sub_scores', [])]
        data['final_score'] = round(sum(voti)/len(voti), 1) if voti else 6.0
        
        return data

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None