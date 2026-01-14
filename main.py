import time
import random
import sys
import os
from datetime import datetime

try:
    from amazon_hunter import get_amazon_data, save_to_db
    from wp_publisher import run_publisher
    from ai_writer import genera_recensione_seo # <--- NUOVO IMPORT
except ImportError as e:
    print(f"❌ ERRORE IMPORT: {e}")
    sys.exit()

def load_asins_from_file(filename="asins.txt"):
    try:
        with open(filename, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def main_loop():
    print("==========================================")
    print(f"🤖 RD-INTELLIGENCE: AI EDITION")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("==========================================\n")

    targets = load_asins_from_file()
    print(f"📋 Caricati {len(targets)} ASIN da monitorare.\n")

    if not targets: return

    # --- FASE 1: RACCOLTA & SCRITTURA AI ---
    print("--- 🕵️‍♂️ FASE 1: RACCOLTA & AI ---")
    for index, asin in enumerate(targets):
        print(f"[{index+1}/{len(targets)}] Caccia su {asin}...")
        
        # 1. Scarica dati da Amazon
        raw_data = get_amazon_data(asin)
        
        # CONTROLLO SICUREZZA: Se Amazon ci ha bloccato (Titolo non trovato), saltiamo
        if raw_data and raw_data['title'] != "Titolo non trovato":
            
            # 2. Generiamo la Recensione con GPT-4o
            # (Lo facciamo solo se il prezzo è > 0 per evitare errori su prodotti non disponibili)
            if raw_data['price'] > 0:
                recensione_html = genera_recensione_seo(raw_data)
                if recensione_html:
                    # Aggiungiamo il testo AI ai dati da salvare
                    # Nota: Dobbiamo essere sicuri che la colonna 'ai_sentiment' o simile esista nel DB
                    # Per ora lo salviamo nel campo 'ai_sentiment' della tabella products
                    raw_data['ai_content'] = recensione_html
                else:
                    raw_data['ai_content'] = "<p>Analisi in corso...</p>"
            else:
                raw_data['ai_content'] = "<p>Prodotto attualmente non disponibile.</p>"

            # 3. Salviamo nel DB
            # (Nota: Dovrai aggiornare amazon_hunter.py se vuoi salvare anche il testo AI, 
            # ma per ora salviamo i dati base e l'AI la integriamo dopo se vuoi fare step-by-step.
            # PER SEMPLIFICARE: Salviamo e basta, l'AI la useremo in pubblicazione o modifichiamo save_to_db ora).
            
            save_to_db(raw_data) 
            # *PICCOLO SPOILER: La funzione save_to_db attuale non salva il campo 'ai_sentiment'.
            # Ti darò la modifica per amazon_hunter tra un attimo per chiudere il cerchio.
            
        else:
            print("   ⚠️ Saltato (Captcha Amazon o Titolo non valido).")

        # Pausa Anti-Ban
        if index < len(targets) - 1:
            wait_time = random.randint(10, 30) # Aumentiamo un po' la pausa
            print(f"   ☕ Pausa {wait_time}s...")
            time.sleep(wait_time)
    
    print("\n✅ Fase Raccolta completata.\n")

    # --- FASE 2: PUBBLICAZIONE ---
    print("--- ✍️ FASE 2: PUBBLICAZIONE WORDPRESS ---")
    run_publisher()

    print("\n==========================================")
    print("🎉 CICLO COMPLETATO.")
    print("==========================================")

if __name__ == "__main__":
    print("♾️  MODALITÀ LOOP ATTIVATA (AI POWERED)")
    while True:
        main_loop()
        sleep_seconds = 3600 + random.randint(1, 600) 
        print(f"\n💤 Dormo per {sleep_seconds/60:.0f} minuti...")
        time.sleep(sleep_seconds)