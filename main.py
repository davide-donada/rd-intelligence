# In alto aggiungi:
from price_updater import update_prices_loop

# ... (il resto del codice main.py) ...

if __name__ == "__main__":
    print("♾️  SISTEMA ATTIVO (HUNTER + PUBLISHER + UPDATER)")
    
    cycle_count = 0
    
    while True:
        # 1. Cerca nuovi prodotti e pubblica
        lavorato = main_loop()
        
        # 2. Ogni 10 cicli (circa ogni 10 minuti se lavora, o 1 ora se dorme), controlla i prezzi
        cycle_count += 1
        if cycle_count >= 10:
            print("Checking aggiornamenti prezzi...")
            update_prices_loop()
            cycle_count = 0 # Reset
            
        if not lavorato:
            time.sleep(60)