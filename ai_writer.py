import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# LA TUA MAPPA CATEGORIE
CATEGORIES_MAP = {
    'Accessori': 3467, 'Alimentazione': 996, 'Alimenti per tutti': 3476, 'Alimenti sportivi': 3475, 'Altri veicoli': 3464, 'App': 179, 'Apple': 801, 'Asciugacapelli': 3635, 'Aspirapolveri': 3627, 'Audio': 3452, 'Automobili': 3453, 'Beauty': 3647, 'Business': 3462, 'Calcio': 3630, 'Componenti': 3528, 'Computer': 83, 'Concerti': 3637, 'Cuffie': 78, 'Cultura': 3459, 'Cybersecurity': 3646, 'Display': 3457, 'Dispositivi medici': 3642, 'Droni': 3505, 'E-mobility': 3473, 'Elettrodomestici': 3612, 'Eventi': 3461, 'Film': 320, 'Fotocamere': 45, 'Fotografia': 3455, 'Friggitrici ad aria': 3632, 'Giochi da tavolo': 3631, 'Hard disk': 3640, 'Istruzione': 3648, 'Lifestyle': 3460, 'Luci': 3660, 'Macchine del caffè': 3623, 'Microfoni': 3565, 'Mobile': 3454, 'Moda': 3539, 'Monitors': 3458, 'Motori': 728, 'Mouse': 3563, 'Musei': 3633, 'Musica': 3639, 'NAS': 3645, 'Neonati': 3641, 'Networking': 3466, 'Occhiali': 3649, 'PC': 3469, 'Periferiche': 3562, 'Power bank': 3634, "Purificatori d'aria": 3644, 'Rasoi': 3636, 'Repeater': 3659, 'Ristoranti': 3474, 'Robot da cucina': 3658, 'Salute': 3621, 'Scooter': 3628, 'Serie TV': 356, 'Smart Home': 624, 'Smartphone': 7, 'Smartwatch': 567, 'Social Networks': 3581, 'Software': 3583, 'Soundbar': 3471, 'Spazzolini elettrici': 3638, 'Speakers': 3470, 'Spettacolo': 3363, 'Sport': 3463, 'Stampanti': 3472, 'Tablet': 8, 'Tastiere': 3516, 'Teatro': 3624, 'Tecnologia': 9, 'Televisori': 3465, 'Traduttori': 3656, 'Trend': 3663, 'Utensili da cucina': 3643, 'Videocamere': 3456, 'Videogiochi': 66, 'Wearable': 851
}

def genera_recensione_seo(prodotto):
    print(f"🧠 AI: Analisi Contenuto + Categoria per '{prodotto['title']}'...")

    prompt_system = f"""
    Sei un redattore esperto di RecensioneDigitale.it.
    Devi scrivere una recensione HTML strutturata e scegliere la categoria corretta.
    
    LISTA CATEGORIE (Nome: ID):
    {json.dumps(CATEGORIES_MAP)}
    """

    prompt_user = f"""
    Scrivi recensione per: {prodotto['title']} ({prodotto['price']}€).
    
    Restituisci un JSON:
    {{
        "html_content": "Codice HTML completo...",
        "category_id": 123
    }}
    
    ISTRUZIONI OBBLIGATORIE PER L'HTML:
    1. Usa <h2> per i titoli delle sezioni.
    2. DIVIETO di usare 4/5 o 5/5. Usa SOLO scala 0-10 (es. 8.5/10).
    3. Il voto finale va in un tag <h3>Voto: X/10</h3>.

    4. STRUTTURA PRO E CONTRO (Segui esattamente questo schema):
       Non fare un elenco misto. Crea due liste separate.
       
       <h3>✅ Pro</h3>
       <ul>
           <li>Scrivi qui il punto di forza (SENZA scrivere 'Pro:' all'inizio)</li>
           <li>Altro punto di forza</li>
       </ul>

       <h3>❌ Contro</h3>
       <ul>
           <li>Scrivi qui il difetto (SENZA scrivere 'Contro:' all'inizio)</li>
           <li>Altro difetto</li>
       </ul>
       
    Sii sintetico, professionale e diretto.
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
        return json.loads(content)

    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return {"html_content": "<p>Errore generazione.</p>", "category_id": 9}