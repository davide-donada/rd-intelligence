import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
    title = product_data.get('title', 'Prodotto')
    price = product_data.get('price', 0)
    features = product_data.get('features', '')
    cat_list = ", ".join(CATEGORIES_MAP.keys())

    prompt_system = f"""
    Sei il Capo Redattore di RecensioneDigitale.it. Scrivi in HTML (usa <h2>, <h3>, <p>, <ul>).
    MAI usare markdown (**grassetto** o # Titolo).
    
    REGOLE CRITICHE:
    1. Voti 0-10 reali. Sii severo se il prezzo ({price}€) è alto.
    2. NON scrivere il voto finale o i voti parziali dentro il testo HTML.
    3. Il testo deve finire con la conclusione discorsiva.
    
    Scegli una categoria tra: [{cat_list}].
    
    JSON: {{
        "html_content": "...",
        "meta_description": "...",
        "category_id": "NomeCategoria",
        "sub_scores": [
            {{ "label": "Qualità Costruttiva", "value": 6.5 }},
            {{ "label": "Prestazioni", "value": 8.0 }},
            {{ "label": "Rapporto Qualità/Prezzo", "value": 5.0 }},
            {{ "label": "Facilità d'uso", "value": 7.5 }}
        ],
        "verdict_badge": "Consigliato",
        "faqs": []
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt_system}, {"role": "user", "content": f"Prodotto: {title}. Dati: {features}"}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        
        # Calcolo media voti dinamica
        voti = [s['value'] for s in data.get('sub_scores', [])]
        data['final_score'] = round(sum(voti)/len(voti), 1) if voti else 6.0
        
        # Match categoria
        name = data.get('category_id')
        data['category_id'] = CATEGORIES_MAP.get(name, 1)
        return data
    except Exception as e:
        print(f"Errore AI: {e}")
        return None