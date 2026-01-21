import os
import json
import requests
from openai import OpenAI

# Configurazione Client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Fallback statico
DEFAULT_MAP = {
    'Tecnologia': 1, 'Smartphone': 60, 'Informatica': 3454, 'Elettrodomestici': 3612
}

def get_live_categories():
    """Scarica le categorie reali dal sito WordPress."""
    url = "https://www.recensionedigitale.it/wp-json/wp/v2/categories?per_page=100&hide_empty=false"
    print("   🌍 Aggiornamento lista categorie da WordPress...")
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            cats = resp.json()
            live_map = {c['name']: c['id'] for c in cats}
            print(f"   ✅ Mappate {len(live_map)} categorie dal sito.")
            return live_map
    except Exception as e:
        print(f"   ⚠️ Errore fetch categorie: {e}")
    return DEFAULT_MAP

# Carichiamo la mappa all'avvio
CATEGORIES_MAP = get_live_categories()

def genera_recensione_seo(product_data):
    title = product_data.get('title', 'Prodotto')
    price = product_data.get('price', 0)
    cat_list_str = ", ".join(CATEGORIES_MAP.keys())

    prompt_system = f"""
    Sei il Capo Redattore di RecensioneDigitale.it.
    
    COMPITO:
    Scrivi ESCLUSIVAMENTE il corpo testuale della recensione in HTML.
    
    STRUTTURA OBBLIGATORIA (Usa solo queste sezioni):
    1. <h2>Recensione [Nome Prodotto]</h2>
    2. <h3>Introduzione</h3> (Descrizione generale)
    3. <h3>Design e Caratteristiche</h3>
    4. <h3>Performance e Utilizzo</h3>
    5. <h3>Conclusioni</h3>
    
    ⚠️ DIVIETI ASSOLUTI (NON INSERIRE NEL TESTO HTML):
    ❌ NON scrivere la sezione "Pro e Contro".
    ❌ NON inserire liste puntate di vantaggi o svantaggi.
    ❌ NON scrivere il "Verdetto Finale" o i voti numerici.
    (Questi dati devono essere inseriti SOLO nel JSON, ci penserà il sito a mostrarli graficamente).
    
    CATEGORIA:
    Scegli una categoria ESATTA dalla lista: [{cat_list_str}]
    
    JSON RICHIESTO:
    {{
        "html_content": "Il testo HTML della recensione (senza pro/contro/voti)",
        "meta_description": "Riassunto SEO di 160 caratteri",
        "category_name": "Nome esatto categoria",
        "pros": ["Punto a favore 1", "Punto a favore 2", "Punto a favore 3"],
        "cons": ["Difetto 1", "Difetto 2"],
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": 8.0 }},
            {{ "label": "Prestazioni", "value": 8.5 }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": f"Titolo: {title}. Prezzo: {price}€"}
            ],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        
        # MAPPING CATEGORIA
        chosen_name = data.get('category_name', '')
        final_id = CATEGORIES_MAP.get(chosen_name)
        if not final_id:
            for key, val in CATEGORIES_MAP.items():
                if chosen_name.lower() in key.lower() or key.lower() in chosen_name.lower():
                    final_id = val
                    data['category_name'] = key
                    break
        data['category_id'] = final_id if final_id else 1
        
        # CALCOLO MEDIA VOTI
        voti = [s['value'] for s in data.get('sub_scores', [])]
        data['final_score'] = round(sum(voti)/len(voti), 1) if voti else 6.0
        
        return data

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None