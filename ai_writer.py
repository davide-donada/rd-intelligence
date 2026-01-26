import os
import json
import requests
from openai import OpenAI

# Configurazione Client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Fallback statico per le categorie
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
    price = product_data.get('current_price', 'N/A')
    
    print(f"   🧠 AI al lavoro su: {title}...")

    prompt_system = f"""
    Sei un recensore esperto di tecnologia ed elettrodomestici per il blog italiano "RecensioneDigitale.it".
    Scrivi una recensione approfondita, onesta e ottimizzata SEO per il prodotto indicato.
    
    REGOLE FONDAMENTALI:
    1. Usa un tono professionale ma accessibile, terza persona plurale ("Abbiamo testato...").
    2. Struttura l'articolo in HTML pulito (senza tag <html> o <body>, usa solo <h2>, <h3>, <p>).
    3. NON includere il titolo H1 o il prezzo nel testo (sono gestiti a parte).
    4. Includi una sezione "Conclusioni" netta.
    5. Genera un JSON valido con i campi richiesti.

    OUTPUT JSON RICHIESTO:
    {{
        "html_content": "<p>Intro...</p><h3>Design</h3><p>...</p>...",
        "meta_description": "Una frase accattivante per Google (max 150 caratteri).",
        "category_name": "Scegli la categoria più adatta tra: {', '.join(CATEGORIES_MAP.keys())}",
        "final_score": 8.5 (numero float da 0 a 10),
        "pros": ["Pro 1", "Pro 2", "Pro 3"],
        "cons": ["Difetto 1", "Difetto 2"],
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": 8.0 }},
            {{ "label": "Prestazioni", "value": 8.5 }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato",
        "faqs": [
            {{ "question": "Domanda frequente 1?", "answer": "Risposta breve e precisa." }},
            {{ "question": "Domanda frequente 2?", "answer": "Risposta." }},
            {{ "question": "Domanda frequente 3?", "answer": "Risposta." }}
        ]
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
            # Ricerca fuzzy semplice
            for key, val in CATEGORIES_MAP.items():
                if chosen_name.lower() in key.lower() or key.lower() in chosen_name.lower():
                    final_id = val
                    data['category_name'] = key
                    break
        data['category_id'] = final_id if final_id else 1
        
        return data

    except Exception as e:
        print(f"   ❌ Errore OpenAI: {e}")
        return None