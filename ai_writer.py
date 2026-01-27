import os
import json
import requests
from openai import OpenAI
import statistics
import random

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
    
    print(f"   🧠 AI (Critico Severo) al lavoro su: {title}...")

    # PROMPT AGGIORNATO: LOGICA DI VOTO "CATTIVA"
    prompt_system = f"""
    Sei un recensore tecnologico ESPERTO, SEVERO e IMPARZIALE per "RecensioneDigitale.it".
    Il tuo compito NON è vendere il prodotto, ma analizzarlo criticamente.
    
    ANALISI DEL PREZZO: Il prodotto costa {price}€. 
    - Se costa poco (<30€), la qualità costruttiva NON può essere 9. Sii realistico (es. 6.5 o 7.0).
    - Se costa tanto, pretendi la perfezione.
    
    GUIDA AI VOTI (Seguila rigorosamente):
    - 5.0 - 6.9: Prodotto economico, "plasticoso", funzioni base o difetti evidenti. (NON AVER PAURA DI USARE QUESTI VOTI).
    - 7.0 - 7.9: Prodotto nella media. Fa il suo dovere, ma non emoziona. "Buono ma non ottimo".
    - 8.0 - 8.8: Ottimo prodotto. Solido, affidabile, consigliato.
    - 9.0 - 10.0: Eccellenza assoluta, innovativo, materiali premium. (USARE RARAMENTE).
    
    REGOLE DI SCRITTURA:
    1. Tono professionale, terza persona plurale ("Abbiamo testato...").
    2. HTML pulito (<h2>, <h3>, <p>). Niente H1 o Prezzo nel testo.
    3. FAQ REALI: 3 domande specifiche che un utente farebbe (es. "Durata batteria", "Rumorosità").
    
    OUTPUT JSON RICHIESTO:
    {{
        "html_content": "<p>Intro...</p><h3>Design</h3><p>...</p>...",
        "meta_description": "Massimo 150 caratteri.",
        "category_name": "Una tra: {', '.join(CATEGORIES_MAP.keys())}",
        "final_score": 0.0, // Lascia 0, lo calcoliamo noi.
        "pros": ["Pro 1", "Pro 2", "Pro 3"],
        "cons": ["Difetto 1", "Difetto 2"],
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": 7.0 }}, // Varia in base al prezzo/materiali!
            {{ "label": "Prestazioni", "value": 8.0 }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato", // O "Economico", "Discreto", "Top", "Nella Media"
        "faqs": [
            {{ "question": "Domanda reale specifica?", "answer": "Risposta." }},
            {{ "question": "Domanda reale?", "answer": "Risposta." }},
            {{ "question": "Domanda reale?", "answer": "Risposta." }}
        ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": f"Analizza: {title}. Prezzo: {price}€"}
            ],
            response_format={"type": "json_object"},
            temperature=0.7 # Un po' di creatività per variare i giudizi
        )
        data = json.loads(response.choices[0].message.content)
        
        # --- CALCOLO MATEMATICO DEL VOTO ---
        if 'sub_scores' in data and data['sub_scores']:
            values = [float(item['value']) for item in data['sub_scores']]
            real_avg = statistics.mean(values)
            data['final_score'] = round(real_avg, 1)
        else:
            data['final_score'] = 7.5 # Fallback più basso di prima

        # Determina il Badge in base al voto reale
        score = data['final_score']
        if score >= 9.0: data['verdict_badge'] = "Eccellente"
        elif score >= 8.0: data['verdict_badge'] = "Consigliato"
        elif score >= 7.0: data['verdict_badge'] = "Buono"
        elif score >= 6.0: data['verdict_badge'] = "Economico"
        else: data['verdict_badge'] = "Sconsigliato"

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
        
        return data

    except Exception as e:
        print(f"   ❌ Errore OpenAI: {e}")
        return None