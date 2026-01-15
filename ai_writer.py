import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def genera_recensione_seo(prodotto):
    print(f"🧠 AI: Scrivo articolo HTML per '{prodotto['title']}'...")

    prompt_system = """
    Sei un redattore esperto di RecensioneDigitale.it.
    Scrivi recensioni in terza persona plurale ("Abbiamo testato", "Riteniamo").
    Il tuo output deve essere SOLO codice HTML (senza tag <html> o <body>).
    Usa tag come <h2>, <p>, <ul>, <li>, <strong>.
    """

    prompt_user = f"""
    Scrivi una recensione completa per: {prodotto['title']}
    Prezzo: {prodotto['price']}€
    ASIN: {prodotto['asin']}

    STRUTTURA OBBLIGATORIA (in HTML):
    1. <h2>Introduzione</h2>: Breve e accattivante.
    2. <h2>Caratteristiche e Prova</h2>: Analisi del prodotto.
    3. <h2>Pro e Contro</h2>: Usa due liste HTML separate.
       - Una lista <ul> con titolo "✅ Cosa ci piace"
       - Una lista <ul> con titolo "❌ Cosa non ci piace"
    4. <h2>Verdetto</h2>: Conclusione sintetica.
    5. <h3>Voto Finale: X/10</h3> (Mettilo ben visibile in un tag <h3>).

    Non aggiungere altro testo fuori dall'HTML.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.replace("```html", "").replace("```", "")

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None