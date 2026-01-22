import mysql.connector
import os
import time
from datetime import datetime

# --- CONFIGURAZIONE DATABASE ---
# Utilizza le variabili d'ambiente per la sicurezza (impostate su Coolify)
# Fallback sui dati inseriti per l'uso in locale
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD', 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

# --- DEFINIZIONE COLORI ANSI ---
C_RESET  = "\033[0m"
C_RED    = "\033[91m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE   = "\033[94m"
C_CYAN   = "\033[96m"
C_BOLD   = "\033[1m"

def get_db_connection():
    """Crea una nuova connessione al database MySQL."""
    return mysql.connector.connect(**DB_CONFIG)

def clear_screen():
    """Pulisce il terminale a seconda del sistema operativo."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_recent_price_moves(cursor):
    """Recupera gli ultimi 5 movimenti di prezzo salvati nello storico."""
    try:
        query = """
            SELECT p.asin, p.title, h.price, h.recorded_at 
            FROM price_history h 
            JOIN products p ON h.product_id = p.id 
            ORDER BY h.recorded_at DESC LIMIT 5
        """
        cursor.execute(query)
        return cursor.fetchall()
    except Exception:
        return []

def show_status():
    """Visualizza le statistiche, gli ultimi post e gli ultimi cambi prezzo."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Recupero Statistiche Generali
        cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
        stats = dict(cursor.fetchall())
        
        pending = stats.get('pending', 0)
        processing = stats.get('processing', 0)
        published = stats.get('published', 0)
        failed = stats.get('failed', 0)
        draft = stats.get('draft', 0)

        print(f"\n{C_BOLD}{C_CYAN}📊 RECAP SISTEMA (Control Room v2.3){C_RESET}")
        print(f"   ⏳ In Coda (Pending):       {C_CYAN}{pending}{C_RESET}")
        print(f"   ⚙️  In Lavorazione:          {C_YELLOW}{processing}{C_RESET}")
        print(f"   📝 Bozze (Draft):           {C_BLUE}{draft}{C_RESET}")
        print(f"   ✅ Pubblicati:              {C_GREEN}{published}{C_RESET}")
        print(f"   ❌ Falliti (Failed):        {C_RED}{failed}{C_RESET}")
        print("─" * 65)

        # 2. Visualizzazione Ultimi 5 Pubblicati
        print(f"\n{C_GREEN}✅ ULTIMI PUBBLICATI SU WORDPRESS:{C_RESET}")
        # Usiamo ORDER BY id DESC per evitare errori su colonne inesistenti
        cursor.execute("SELECT asin, title, current_price FROM products WHERE status = 'published' ORDER BY id DESC LIMIT 5")
        recents = cursor.fetchall()
        
        print(f"   {'ASIN':<12} | {'PREZZO':<9} | {'TITOLO'}")
        for r in recents:
            title_short = (r[1][:45] + "...") if r[1] else "Titolo non ancora disponibile"
            print(f"   {r[0]:<12} | € {str(r[2]):<7} | {title_short}")

        # 3. Visualizzazione Ultimi Movimenti di Prezzo
        print(f"\n{C_YELLOW}💰 ULTIMI MOVIMENTI PREZZI (Live Tracker):{C_RESET}")
        moves = get_recent_price_moves(cursor)
        if moves:
            print(f"   {'ORARIO':<8} | {'ASIN':<12} | {'PREZZO':<9} | {'TITOLO'}")
            for m in moves:
                time_str = m[3].strftime("%H:%M")
                title_short = (m[1][:38] + "...") if m[1] else "Titolo non disponibile"
                print(f"   {time_str:<8} | {m[0]:<12} | € {str(m[2]):<7} | {title_short}")
        else:
            print("   (Nessuno storico prezzi registrato nell'ultima ora)")

    except Exception as e:
        print(f"{C_RED}❌ Errore durante l'aggiornamento dati: {e}{C_RESET}")
    finally:
        if conn: conn.close()

def add_asin():
    """Aggiunge uno o più ASIN al database in stato 'pending'."""
    print(f"\n{C_BOLD}➕ AGGIUNGI PRODOTTI{C_RESET}")
    asin_input = input(f"Inserisci ASIN (o più ASIN separati da virgola): ").strip()
    
    if not asin_input: return

    # Rimuoviamo eventuali virgolette o apici e dividiamo per virgola
    asin_input = asin_input.replace("'", "").replace('"', '')
    asins = [x.strip().upper() for x in asin_input.split(',')]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added_count = 0
    for asin in asins:
        if len(asin) < 5: continue
        try:
            # Controlliamo se esiste già
            cursor.execute("SELECT id FROM products WHERE asin = %s", (asin,))
            if cursor.fetchone():
                print(f"   ⚠️  {asin} è già presente nel database.")
            else:
                cursor.execute("INSERT INTO products (asin, status, created_at) VALUES (%s, 'pending', NOW())", (asin,))
                added_count += 1
                print(f"   ✅ {asin} aggiunto correttamente alla coda.")
        except Exception as e:
            print(f"   ❌ Errore tecnico con l'ASIN {asin}: {e}")

    conn.commit()
    conn.close()
    print(f"\n--- Operazione conclusa: {added_count} nuovi ASIN in coda ---")
    time.sleep(1.5)

def reset_status(target_status, label):
    """Sblocca o resetta i prodotti con uno stato specifico portandoli a 'pending'."""
    print(f"\n🚑 Reset prodotti '{label}' in corso...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"UPDATE products SET status = 'pending' WHERE status = '{target_status}'")
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            print(f"   ✅ Successo: {count} prodotti sbloccati e riportati in stato 'Pending'.")
        else:
            print(f"   👍 Nessun prodotto in stato '{label}' trovato.")
            
    except Exception as e:
        print(f"❌ Errore Database durante il reset: {e}")
    finally:
        conn.close()
    
    input("\nPremi INVIO per tornare alla dashboard...")

def main_loop():
    """Ciclo principale dell'applicazione terminale."""
    while True:
        clear_screen()
        show_status()
        
        print(f"\n{C_BOLD}COMANDI DISPONIBILI:{C_RESET}")
        print(f" [{C_CYAN}1{C_RESET}] ➕ Aggiungi ASIN Amazon")
        print(f" [{C_CYAN}2{C_RESET}] 🔄 Ricarica Schermata")
        print(f" [{C_CYAN}3{C_RESET}] 🚑 Sblocca 'In Lavorazione' (Reset crash)")
        print(f" [{C_CYAN}4{C_RESET}] ♻️  Riprova prodotti Falliti (Failed)")
        print(f" [{C_RED}q{C_RESET}] 👋 Esci")
        
        choice = input("\nSeleziona un'opzione > ").strip().lower()
        
        if choice == '1':
            add_asin()
        elif choice == '2':
            continue
        elif choice == '3':
            reset_status('processing', 'In Lavorazione')
        elif choice == '4':
            reset_status('failed', 'Falliti')
        elif choice == 'q':
            print("Chiusura pannello admin...")
            break

if __name__ == "__main__":
    main_loop()