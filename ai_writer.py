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
    # print("   🌍 Aggiornamento lista categorie da WordPress...") # Ridotto log
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            cats = resp.json()
            live_map = {c['name']: c['id'] for c in cats}
            return live_map
    except Exception as e:
        print(f"   ⚠️ Errore fetch categorie: {e}")
    return DEFAULT_MAP

# Carichiamo la mappa all'avvio
CATEGORIES_MAP = get_live_categories()

def genera_recensione_seo(product_data):
    title = product_data.get('title', 'Prodotto')
    
    # GESTIONE PREZZO E CONTESTO
    raw_price = product_data.get('price', 0)
    try:
        price_val = float(raw_price)
    except:
        price_val = 0
        
    if price_val > 0:
        price_str = f"€ {price_val:.2f}"
        price_instruction = f"Il prezzo ATTUALE è {price_str}. Questo è il parametro PIÙ IMPORTANTE. Se il prodotto è mediocre ma costa troppo, DEVI PUNIRLO con un voto basso (4, 5, 6). Se costa poco ed è onesto, premialo."
    else:
        price_str = "Non disponibile"
        price_instruction = "Il prezzo non è disponibile. Fai una stima basata sulle specifiche. Se sembra un prodotto 'cheap' (cinesata), trattalo come tale."

    prompt_system = f"""
    Sei un critico tecnologico severo e imparziale per RecensioneDigitale.it.
    Non sei qui per vendere, ma per analizzare la verità.
    
    OGGETTO: {title}
    CONTESTO PREZZO: {price_instruction}
    
    SCALA DI VALUTAZIONE (RISPETTALA RIGOROSAMENTE):
    - 1.0 a 4.9: Pessimo. Soldi buttati, truffa, o qualità inaccettabile.
    - 5.0 a 6.5: Mediocre. Plasticoso, difetti evidenti, o troppo costoso per quel che offre.
    - 6.6 a 7.5: Discreto/Buono. Fa il suo dovere, senza lode e senza infamia.
    - 7.6 a 8.5: Ottimo. Un acquisto solido e consigliato.
    - 8.6 a 9.5: Eccellente. Best Buy della categoria.
    - 9.6 a 10: Perfezione (usare raramente).

    ISTRUZIONI CRITICHE:
    1. NON dare automaticamente 8 o 8.5. Sii vario. Usa i 6 e i 7 se il prodotto è solo "ok".
    2. Se le specifiche sono basse (es. poca RAM, schermo bassa risoluzione) e il prezzo non è stracciato, DISTRUGGILO nella recensione.
    3. Scrivi in terza persona plurale ("Abbiamo testato", "Riteniamo").
    4. Sii sintetico e diretto.
    
    STRUTTURA HTML OBBLIGATORIA:
    - Intro (senza titolo)
    - <h3>Design</h3>
    - <h3>Prestazioni</h3>
    - <h3>[Terzo Aspetto a scelta]</h3>
    
    OUTPUT JSON RICHIESTO:
    {{
        "html_content": "<p>...</p><h3>...</h3>",
        "meta_description": "Riassunto SEO 150 caratteri",
        "category_name": "Categoria",
        "final_score": (numero float CALCOLATO ORA, es. 6.2, 7.8, 9.1 - NON FISSO),
        "pros": ["Pro 1", "Pro 2"],
        "cons": ["Contro 1", "Contro 2"],
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": (voto float) }},
            {{ "label": "Prestazioni", "value": (voto float) }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": (voto float) }}
        ],
        "verdict_badge": "Testo breve (es: 'Da Evitare', 'Economico', 'Best Buy', 'Top')" ,
        "faqs": [
            {{ "question": "...", "answer": "..." }},
            {{ "question": "...", "answer": "..." }},
            {{ "question": "...", "answer": "..." }}
        ]
    }}
    """
    
    print(f"   🧠 AI Analizza: {title} (Prezzo: {price_str})...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sei un critico severo che risponde solo in JSON."},
                {"role": "user", "content": prompt_system}
            ],
            response_format={"type": "json_object"},
            temperature=0.8 # Alzato leggermente per favorire giudizi più "umani" e vari
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        
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
        print(f"   ❌ Errore AI: {e}")
        return {
            "html_content": f"<p>Analisi in corso per {title}.</p>",
            "meta_description": f"Recensione {title}",
            "category_name": "Generale",
            "category_id": 1,
            "final_score": 6.0, # Fallback prudente
            "pros": [],
            "cons": [],
            "sub_scores": [],
            "verdict_badge": "In Valutazione",
            "faqs": []
        }