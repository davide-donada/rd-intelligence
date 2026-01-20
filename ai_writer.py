import os
import json
import random
from openai import OpenAI

# --- CONFIGURAZIONE CLIENT ---
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# --- MAPPA CATEGORIE WORDPRESS ---
CATEGORIES_MAP = {
    'Accessori': 3467, 'Alimentazione': 996, 'Alimenti per tutti': 3476, 
    'Alimenti sportivi': 3475, 'Altri veicoli': 3464, 'App': 179, 'Apple': 801, 
    'Asciugacapelli': 3635, 'Aspirapolveri': 3627, 'Audio': 3452, 
    'Automobili': 3453, 'Beauty': 3647, 'Business': 3462, 'Calcio': 3630, 
    'Componenti': 3528, 'Computer': 83, 'Concerti': 3637, 'Cuffie': 78, 
    'Cultura': 3459, 'Cybersecurity': 3646, 'Display': 3457, 
    'Dispositivi medici': 3642, 'Droni': 3505, 'E-mobility': 3473, 
    'Elettrodomestici': 3612, 'Eventi': 3461, 'Film': 320, 'Fotocamere': 45, 
    'Fotografia': 3455, 'Friggitrici ad aria': 3632, 'Giochi da tavolo': 3466, 
    'Giochi e Console': 3456, 'Hardware': 3468, 'Home Cinema': 3636, 
    'Informatica': 3454, 'Integratori': 3643, 'Intelligenza Artificiale': 3645, 
    'Internet': 178, 'Istruzione': 3460, 'Libri': 3458, 'Mobile': 3470, 
    'Moda': 3474, 'Monopattini': 3639, 'Moto': 3633, 'Motori': 3629, 
    'Musica': 3465, 'Nutrizione': 3641, 'Oggettistica': 3648, 'PC': 3469, 
    'Periferiche': 3631, 'Prodotti per la casa': 3649, 'Robot da cucina': 3626, 
    'Salute': 3640, 'Scienza': 3644, 'Sicurezza': 3472, 'Smart Home': 3628, 
    'Smartphone': 60, 'Social': 3463, 'Software': 177, 'Sport': 3638, 
    'Tablet': 3471, 'Tecnologia': 1, 'Telefonia': 59, 'TV': 3634, 
    'Videogiochi': 118, 'Wearable': 3500, 'Web': 176
}

def genera_recensione_seo(product_data):
    title = product_data.get('title', 'Prodotto sconosciuto')
    price = product_data.get('price', 0)
    features = product_data.get('features', '')

    print(f"      🧠 [AI] Scrivo recensione strutturata: {title[:30]}...")
    
    # Prepariamo la lista delle categorie come stringa per il prompt
    cat_list_str = ", ".join(CATEGORIES_MAP.keys())

    # PROMPT BLINDATO SULLA STRUTTURA + CATEGORIE
    prompt_system = f"""
    Sei il Capo Redattore Tecnico di RecensioneDigitale.it.
    Il tuo compito è scrivere una recensione approfondita, critica e perfettamente formattata in HTML.
    
    ⚠️ DIVIETO ASSOLUTO DI MARKDOWN:
    - NON usare MAI asterischi doppi (**Titolo**) per i titoli.
    - NON usare MAI cancelletti (## Titolo).
    - DEVI usare i tag HTML: <h2>Per i titoli principali</h2>, <h3>Per i sottotitoli</h3>.
    
    SCHEMA OBBLIGATORIO ARTICOLO (Segui questo ordine):
    1. <p>Introduzione discorsiva (chi siamo, cosa testiamo, prime impressioni).</p>
    2. <h2>Design e Qualità Costruttiva</h2> + <p>Analisi materiali, ergonomia, peso...</p>
    3. <h2>Caratteristiche Tecniche e Display</h2> + <p>Analisi specifiche, schermo, luminosità...</p>
    4. <h2>Esperienza d'Uso e Prestazioni</h2> + <p>Come si comporta nell'uso reale? Lag? Velocità?</p>
    5. <h2>Autonomia e Ricarica</h2> (Se applicabile) o <h2>Funzionalità Extra</h2>
    6. <h3>✅ Pro</h3> (Usa una lista <ul><li>...</li></ul>)
    7. <h3>❌ Contro</h3> (Usa una lista <ul><li>...</li></ul>)
    
    CATEGORIA:
    Scegli la categoria più adatta ESCLUSIVAMENTE da questa lista:
    [{cat_list_str}]
    Nel campo 'category_id' del JSON, restituisci IL NOME esatto della categoria scelta (es. "Smartphone").
    
    TONO DI VOCE:
    - Terza persona plurale ("Abbiamo testato", "Riteniamo che").
    - Sii critico: Se costa tanto (sopra 100€) e vale poco, dillo chiaramente.
    - Sii onesto: Scala voti 0-10 reale. Non aver paura di dare 4 o 5 se meritato.
    
    OUTPUT JSON RICHIESTO:
    {{
        "html_content": "<p>...</p><h2>Design</h2><p>...</p>...",
        "meta_description": "Frase SEO di 150 caratteri.",
        "category_id": "Smartphone", 
        "sub_scores": [
            {{"label": "Design", "value": 7.0}},
            {{"label": "Prestazioni", "value": 8.0}},
            {{"label": "Prezzo", "value": 5.0}},
            {{"label": "Qualità", "value": 6.5}}
        ],
        "verdict_badge": "Buono",
        "faqs": [{{"question": "...", "answer": "..."}}]
    }}
    """

    prompt_user = f"""
    Scrivi la recensione COMPLETA per:
    PRODOTTO: {title}
    PREZZO: {price}€
    DATI: {features}
    
    IMPORTANTE:
    - Voglio almeno 400 parole di testo.
    - Non fare elenchi puntati lunghi, scrivi paragrafi discorsivi.
    - SEZIONA il testo con i tag <h2>. Non fare un muro di testo unico.
    - Valuta severamente il rapporto qualità/prezzo.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.7, 
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        ai_data = json.loads(content)
        
        # --- CALCOLO MATEMATICO VOTI ---
        if 'sub_scores' in ai_data and len(ai_data['sub_scores']) > 0:
            total = sum(item['value'] for item in ai_data['sub_scores'])
            count = len(ai_data['sub_scores'])
            math_score = total / count
            # Arrotondamento al mezzo punto (es. 7.5)
            final_score = round(math_score * 2) / 2
            ai_data['final_score'] = final_score
        else:
            ai_data['final_score'] = 6.0

        # --- MATCHING CATEGORIA (FIX) ---
        chosen_cat = ai_data.get('category_id')
        real_cat_id = 1 # Fallback: Uncategorized
        
        print(f"      🗂️  AI ha scelto la categoria: '{chosen_cat}'")

        if isinstance(chosen_cat, int):
            # Se per miracolo l'AI indovina l'ID
            real_cat_id = chosen_cat
        elif isinstance(chosen_cat, str):
            # 1. Tentativo Esatto
            if chosen_cat in CATEGORIES_MAP:
                real_cat_id = CATEGORIES_MAP[chosen_cat]
            else:
                # 2. Tentativo "Fuzzy" (parziale)
                # Utile se l'AI scrive "Smartphones" invece di "Smartphone"
                for key in CATEGORIES_MAP:
                    if key.lower() in chosen_cat.lower() or chosen_cat.lower() in key.lower():
                        real_cat_id = CATEGORIES_MAP[key]
                        break
        
        ai_data['category_id'] = real_cat_id
        print(f"      ✅ Mappata a ID: {real_cat_id}")

        return ai_data

    except Exception as e:
        print(f"      ❌ Errore OpenAI: {e}")
        return None