import os
from openai import OpenAI
import json

# Legge la chiave API dalle variabili d'ambiente
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def genera_recensione_seo(prodotto):
    """
    Usa GPT-4o per scrivere una recensione completa basata sui dati grezzi.
    prodotto = {'title': '...', 'price': 10.99, 'asin': '...'}
    """
    print(f"🧠 AI: Sto scrivendo la recensione per '{prodotto['title']}'...")

    prompt_system = """
    Sei un redattore esperto di tecnologia e prodotti consumer per il sito RecensioneDigitale.it.
    Il tuo obiettivo è scrivere recensioni utili, oneste e ottimizzate SEO.
    
    LINEE GUIDA:
    1. Scrivi SEMPRE in terza persona plurale ("Abbiamo testato...", "Riteniamo che...").
    2. Tono professionale ma accessibile, mai stile "comunicato stampa".
    3. Struttura HTML pulita (usa <h2>, <p>, <ul>, <strong>).
    4. La recensione deve sembrare scritta da chi ha provato il prodotto.
    5. NON inventare specifiche tecniche se non le sai, basati sulla plausibilità e sul titolo.
    """

    prompt_user = f"""
    Scrivi una recensione completa per questo prodotto:
    Nome: {prodotto['title']}
    Prezzo Attuale: {prodotto['price']}€
    ASIN: {prodotto['asin']}

    LA RECENSIONE DEVE CONTENERE:
    1. Un'introduzione accattivante (ottica SEO).
    2. Analisi delle caratteristiche principali (deduci dal nome del prodotto).
    3. Un elenco puntato di PRO e CONTRO.
    4. CONCLUSIONE con un Voto Numerico (da 1 a 10) ben visibile.
    5. Includi una Meta Description alla fine (in un tag <meta_desc> invisibile o separato).

    Restituisci SOLO il codice HTML del corpo dell'articolo (senza <html> o <body>).
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # O "gpt-3.5-turbo" se vuoi risparmiare
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.7
        )
        
        contenuto = response.choices[0].message.content
        return contenuto.replace("```html", "").replace("```", "") # Pulizia markdown

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None