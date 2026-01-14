import time
import random
import sys
from datetime import datetime

# IMPORTIAMO GLI "OPERAI" CHE HAI GIA' SCRITTO
# Se ti dà errore qui, controlla che i file si chiamino esattamente così
try:
    from amazon_hunter import get_amazon_data, save_to_db
    from wp_publisher import run_publisher
except ImportError as e:
    print("❌ ERRORE: Non trovo i file 'amazon_hunter.py' o 'wp_publisher.py'.")
    print(f"Dettaglio: {e}")
    sys.exit()

def load_asins_from_file(filename="asins.txt"):
    """Legge la lista degli ASIN dal file di testo"""
    try:
        with open(filename, "r") as f:
            # Pulisce le righe da spazi vuoti e invio
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"❌ Errore: Crea il file '{filename}' con un ASIN per riga!")
        return []

def main_loop():
    print("==========================================")
    print(f"🤖 RD-INTELLIGENCE: AVVIO SISTEMA")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("==========================================\n")

    # 1. CARICAMENTO OBIETTIVI
    targets = load_asins_from_file()
    print(f"📋 Caricati {len(targets)} ASIN da monitorare.\n")

    if not targets:
        return

    # 2. FASE DI CACCIA (Scraping)
    print("--- 🕵️‍♂️ FASE 1: RACCOLTA DATI AMAZON ---")
    for index, asin in enumerate(targets):
        print(f"[{index+1}/{len(targets)}] Elaborazione {asin}...")
        
        # A. Scarica i dati
        data = get_amazon_data(asin)
        
        if data:
            # B. Salva nel DB (che è sul Server)
            save_to_db(data)
        else:
            print("   ⚠️ Saltato per errore scraping.")

        # C. Pausa Tattica (ANTIBAN)
        # Fondamentale: non martellare Amazon. Aspetta tra 5 e 15 secondi a caso.
        if index < len(targets) - 1:
            wait_time = random.randint(5, 15)
            print(f"   ☕ Pausa caffè di {wait_time} secondi anti-ban...")
            time.sleep(wait_time)
    
    print("\n✅ Raccolta dati completata.\n")

    # 3. FASE DI PUBBLICAZIONE (WordPress)
    print("--- ✍️ FASE 2: GENERAZIONE CONTENUTI ---")
    # Questo script legge dal DB quali sono nuovi ('draft') e li pubblica
    run_publisher()

    print("\n==========================================")
    print("🎉 CICLO COMPLETATO. BUON LAVORO DIRETTORE.")
    print("==========================================")

if __name__ == "__main__":
    print("♾️  MODALITÀ LOOP ATTIVATA: Premi CTRL+C per fermare.")
    
    while True:
        main_loop()
        
        # Calcoliamo quanto dormire (es. 1 ora = 3600 secondi)
        # Mettiamo un po' di casualità per sembrare umani anche nel ritmo
        sleep_seconds = 3600 + random.randint(1, 300) 
        
        print(f"\n💤 Tutto fatto. Dormo per {sleep_seconds/60:.0f} minuti (fino al prossimo giro)...")
        time.sleep(sleep_seconds)