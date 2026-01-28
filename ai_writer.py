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
    
    # GESTIONE PREZZO INTELLIGENTE
    raw_price = product_data.get('price', 0)
    try:
        price_val = float(raw_price)
    except:
        price_val = 0
        
    if price_val > 0:
        price_str = f"€ {price_val:.2f}"
        price_instruction = f"Il prezzo ATTUALE è {price_str}. BASA IL VOTO E IL GIUDIZIO 'RAPPORTO QUALITÀ/PREZZO' ESCLUSIVAMENTE SU QUESTO VALORE. Non scrivere MAI 'prezzo non disponibile' o 'non specificato'."
    else:
        price_str = "Non disponibile al momento"
        price_instruction = "Il prezzo esatto non è disponibile al momento. STIMA il prezzo in base alle specifiche tecniche (fascia bassa, media o alta) e al brand per dare un giudizio verosimile. Non scrivere 'prezzo sconosciuto', scrivi 'considerando la fascia di mercato...'."

    prompt_system = f"""
    Sei un recensore esperto di tecnologia e prodotti consumer per il sito RecensioneDigitale.it.
    Il tuo compito è scrivere una recensione onesta, dettagliata e ottimizzata SEO per il prodotto specificato.
    
    DATI PRODOTTO:
    Nome: {title}
    {price_instruction}
    
    STRUTTURA OBBLIGATORIA (HTML):
    1. Un paragrafo introduttivo (senza titolo "Introduzione") che riassume il prodotto e a chi è rivolto.
    2. <h3>Design</h3>: Analisi estetica e materiali.
    3. <h3>Prestazioni</h3>: Come si comporta nell'uso reale.
    4. <h3>[Altra Caratteristica Rilevante]</h3>: Scegli tu (es. Display, Autonomia, Pulizia, Suono) in base al tipo di prodotto.
    
    REGOLE DI SCRITTURA:
    - Scrivi in ITALIANO perfetto.
    - Usa la terza persona plurale ("Abbiamo testato", "La nostra opinione").
    - Sii critico: non sembrare un comunicato stampa. Se il prodotto costa poco, aspettati difetti. Se costa tanto, pretendi perfezione.
    - NON usare frasi come "In conclusione", "Tirando le somme".
    - Lunghezza ideale: circa 400-500 parole.
    
    OUTPUT RICHIESTO (JSON PURO):
    Devi restituire UN SOLO oggetto JSON con questa struttura esatta:
    {{
        "html_content": "Testo della recensione in HTML (paragrafi <p> e titoli <h3>)",
        "meta_description": "Riassunto SEO di 150 caratteri per Google",
        "category_name": "Una categoria pertinente (es. Smartphone, Audio, Casa, Cucina)",
        "final_score": 8.5 (numero float da 0 a 10, basato rigorosamente sul rapporto qualità/prezzo di {price_str}),
        "pros": ["Pro 1", "Pro 2", "Pro 3"],
        "cons": ["Contro 1", "Contro 2"],
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": 8.0 }},
            {{ "label": "Prestazioni", "value": 8.5 }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato" (o "Best Buy", "Economico", "Top di Gamma", "Da Evitare" in base al voto),
        "faqs": [
            {{ "question": "Domanda pertinente 1?", "answer": "Risposta breve." }},
            {{ "question": "Domanda pertinente 2?", "answer": "Risposta breve." }},
            {{ "question": "Domanda pertinente 3?", "answer": "Risposta breve." }}
        ]
    }}
    """
    
    print(f"   🧠 AI sta scrivendo la recensione per: {title} (Prezzo: {price_str})...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sei un assistente editoriale JSON."},
                {"role": "user", "content": prompt_system}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        
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
        print(f"   ❌ Errore AI: {e}")
        # Return fallback data per non bloccare il sistema
        return {
            "html_content": f"<p>Descrizione non disponibile al momento per {title}.</p>",
            "meta_description": f"Recensione {title}",
            "category_name": "Generale",
            "category_id": 1,
            "final_score": 7.0,
            "pros": [],
            "cons": [],
            "sub_scores": [],
            "verdict_badge": "Standard",
            "faqs": []
        }