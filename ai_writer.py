import os
import json
from openai import OpenAI
from datetime import datetime

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Mappa categorie (uguale a prima - la abbrevio qui per leggibilità, tu usa quella completa)
CATEGORIES_MAP = {'Tecnologia': 9, 'Casa': 3612, 'Smartphone': 7, 'Audio': 3452} 
# ... Assicurati di lasciare la tua mappa completa nel file vero!

def genera_recensione_seo(prodotto):
    print(f"🧠 AI: Generazione Scorecard Animata per '{prodotto['title']}'...")

    features = prodotto.get('features', 'Nessuna specifica.')

    prompt_system = f"""
    Sei il Capo Redattore di RecensioneDigitale.it.
    Oltre alla recensione, devi compilare una SCORECARD dettagliata.
    
    CATEGORIE: {json.dumps(CATEGORIES_MAP)}
    """

    prompt_user = f"""
    Prodotto: {prodotto['title']} ({prodotto['price']}€)
    Dettagli: {features}
    
    Genera un JSON con:
    1. HTML Recensione (Intro, Analisi, Pro/Contro).
    2. Meta Description.
    3. Final Score (0-10).
    4. 4 VOTI PARZIALI (Scegli le etichette in base al prodotto, es: "Batteria", "Design", "Suono").
    5. UN VERDETTO BREVE (Max 2 parole, es: "Best Buy", "Consigliato", "Costoso").
    
    OUTPUT JSON:
    {{
        "html_content": "...",
        "meta_description": "...",
        "final_score": 8.5,
        "category_id": 123,
        "verdict_badge": "Best Buy",
        "sub_scores": [
            {{"label": "Qualità/Prezzo", "value": 9}},
            {{"label": "Prestazioni", "value": 8}},
            {{"label": "Design", "value": 8.5}},
            {{"label": "Utilizzo", "value": 9}}
        ]
    }}
    
    REGOLE HTML:
    - Usa <h2>, <p>.
    - Pro/Contro separati (<h3>✅ Pro</h3>... <h3>❌ Contro</h3>...).
    - NON scrivere il voto finale nell'HTML, lo aggiungeremo noi con la grafica.
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
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return {
            "html_content": "<p>Errore.</p>", "category_id": 9, "meta_description": "", 
            "final_score": 8, "verdict_badge": "Buono", 
            "sub_scores": [{"label": "Generale", "value": 8}]
        }