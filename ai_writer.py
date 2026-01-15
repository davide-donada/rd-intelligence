import os
from openai import OpenAI
import json

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def genera_recensione_seo(prodotto):
    print(f"🧠 AI: Scrivo recensione per '{prodotto['title']}'...")

    prompt_system = """
    Sei un redattore esperto per RecensioneDigitale.it.
    Il tuo compito è analizzare il prodotto e restituire un JSON strutturato.
    """

    prompt_user = f"""
    Analizza il prodotto: {prodotto['title']} (Prezzo: {prodotto['price']}€).

    Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura:
    {{
        "review_content": "HTML completo dell'articolo (Intro, Analisi, Conclusioni). NON includere qui il box pro/contro o il voto, verranno aggiunti dal plugin.",
        "final_score": 85, 
        "pros": ["Punto di forza 1", "Punto di forza 2", "Punto di forza 3"],
        "cons": ["Difetto 1", "Difetto 2"],
        "meta_desc": "Meta description ottimizzata SEO (max 160 caratteri)."
    }}

    IMPORTANTE:
    - "final_score": Usa un numero intero da 0 a 100 (Esempio: 85, 92, 70).
    - "review_content": Usa tag <h2>, <p>, <strong>. Sii discorsivo e professionale.
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