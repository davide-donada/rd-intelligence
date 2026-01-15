import os
from openai import OpenAI
import json

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def genera_recensione_seo(prodotto):
    print(f"🧠 AI: Analisi JSON per '{prodotto['title']}'...")

    prompt_system = """
    Sei un redattore esperto per RecensioneDigitale.it.
    Analizza il prodotto e restituisci un JSON rigoroso.
    Tono: Professionale, Terza persona plurale.
    """

    prompt_user = f"""
    Analizza: {prodotto['title']} (ASIN: {prodotto['asin']}, Prezzo: {prodotto['price']}€).

    Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura:
    {{
        "review_content": "HTML dell'articolo (Intro, Analisi, Conclusioni). NON mettere qui pro/contro o tabelle voti.",
        "final_score": 8.5, 
        "pros": ["Pro 1", "Pro 2", "Pro 3"],
        "cons": ["Contro 1", "Contro 2"],
        "meta_desc": "Meta description SEO."
    }}
    
    IMPORTANTE SUL VOTO (final_score):
    Deve essere un numero decimale da 0.0 a 10.0 (Esempio: 7.5, 8.2, 9.0).
    NON usare la scala 100.
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
        return response.choices[0].message.content

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None