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

    print(f"      🧠 [AI] Analizzo severamente: {title[:40]}...")

    # PROMPT SPIETATO
    prompt_system = """
    Sei un critico tecnologico severo e incorruttibile per 'RecensioneDigitale.it'.
    Il tuo compito è giudicare la REALTÀ del prodotto.
    
    LA TUA FILOSOFIA DI VOTO (SCALA 0-10):
    - 0-4 (Pessimo/Insufficiente): Materiali scadenti, promesse false, prezzo folle per quello che offre. NON AVER PAURA DI DARE 3 o 4.
    - 5-6 (Mediocre/Sufficiente): Fa il suo dovere ma nulla di più. Prodotto noioso o con difetti evidenti.
    - 7-8 (Buono/Ottimo): Prodotto solido, vale il prezzo.
    - 9-10 (Eccellente/Perfetto): Rivoluzionario, senza difetti. (I 10 devono essere rari).
    
    NON ESSERE GENTILE. Se un prodotto da 20€ promette di essere come un iPhone, distruggilo nella recensione.
    
    STRUTTURA JSON:
    {
        "html_content": "...",
        "meta_description": "...",
        "category_id": 123,
        "sub_scores": [
            {"label": "Qualità Costruttiva", "value": 4.0},
            {"label": "Prestazioni", "value": 5.5},
            {"label": "Prezzo", "value": 8.0},
            {"label": "Funzionalità", "value": 6.0}
        ],
        "verdict_badge": "Sconsigliato", 
        "faqs": [...]
    }
    
    IMPORTANTE: I 'sub_scores' devono riflettere i difetti. Se scrivi che è plastica scadente, il voto Materiali DEVE essere basso (es. 4.0).
    """

    prompt_user = f"""
    Recensisci questo prodotto:
    TITOLO: {title}
    PREZZO: {price}€
    CARATTERISTICHE: {features}
    
    Analizza il rapporto qualità/prezzo.
    Se è una "cinesata" costosa, puniscilo con voti bassi.
    Se è un top di gamma perfetto, premialo.
    Usa la scala intera da 0 a 10.
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
        
        # --- CALCOLO MATEMATICO PURO (Senza Freni) ---
        if 'sub_scores' in ai_data and len(ai_data['sub_scores']) > 0:
            total = sum(item['value'] for item in ai_data['sub_scores'])
            count = len(ai_data['sub_scores'])
            
            # Media matematica esatta
            math_score = total / count
            
            # Arrotondamento al mezzo punto (es. 7.0, 7.5, 8.0) per pulizia estetica
            # Moltiplico per 2, arrotondo, divido per 2.
            final_score = round(math_score * 2) / 2
            
            # NESSUN LIMITE: Accettiamo tutto da 0.0 a 10.0
            ai_data['final_score'] = final_score
        else:
            ai_data['final_score'] = 6.0 # Fallback neutro se fallisce

        # Mappatura Categorie (Logica invariata)
        chosen_cat = ai_data.get('category_id')
        real_cat_id = 1
        if isinstance(chosen_cat, int):
            real_cat_id = chosen_cat
        elif isinstance(chosen_cat, str) and chosen_cat in CATEGORIES_MAP:
            real_cat_id = CATEGORIES_MAP[chosen_cat]
        else:
            for key in CATEGORIES_MAP:
                if key.lower() in str(chosen_cat).lower():
                    real_cat_id = CATEGORIES_MAP[key]
                    break
        ai_data['category_id'] = real_cat_id

        return ai_data

    except Exception as e:
        print(f"      ❌ Errore OpenAI: {e}")
        return None