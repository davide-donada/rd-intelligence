import mysql.connector
import os
import time
from datetime import datetime

# --- CONFIGURAZIONE ---
# Usa le variabili d'ambiente per sicurezza, con fallback sui tuoi dati
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD', 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

# --- COLORI ANSI ---
C_RESET  = "\033[0m"
C_RED    = "\033[91m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE   = "\033[94m"
C_CYAN   = "\033[96m"
C_BOLD   = "\033[1m"

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_recent_price_moves(cursor):
    """Recupera gli ultimi 5 movimenti di prezzo dallo storico"""
    try:
        query = """
            SELECT p.asin, p.title, h.price, h.recorded_at 
            FROM price_history h 
            JOIN products p ON h.product_id = p.id 
            ORDER BY h.recorded_at DESC LIMIT 5
        """
        cursor.execute(query)
        return cursor.fetchall()
    except:
        return []

def show_status():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Statistiche
        cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
        stats = dict(cursor.fetchall())
        
        pending = stats.get('pending', 0)
        processing = stats.get('processing', 0)
        published = stats.get('published', 0)
        failed = stats.get('failed', 0)
        draft = stats.get('draft', 0)

        print(f"\n{C_BOLD}📊 STATO SERVER (Control Room v2.1):{C_RESET}")
        print(f"   ⏳ In Coda (Pending):       {C_CYAN}{pending}{C_RESET}")
        print(f"   ⚙️  In Lavorazione:          {C_YELLOW}{processing}{C_RESET}")
        print(f"   📝 Bozze (Draft):           {C_BLUE}{draft}{C_RESET}")
        print(f"   ✅ Pubblicati:              {C_GREEN}{published}{C_RESET}")
        print(f"   ❌ Errori (Failed):         {C_RED}{failed}{C_RESET}")
        print("─" * 60)

        # 2. Ultimi Pubblicati (CORRETTO: ORDER BY id DESC)
        print(f"\n{C_GREEN}✅ ULTIMI PUBBLICATI SU WORDPRESS:{C_RESET}")
        # Qui usiamo ID invece di updated_at per evitare errori
        cursor.execute("SELECT asin, title, current_price FROM products WHERE status = 'published' ORDER BY id DESC LIMIT 5")
        recents = cursor.fetchall()
        print(f"   {'ASIN':<12} | {'PREZZO':<10} | {'TITOLO'}")
        for r in recents:
            title_short = (r[1][:45] + "...") if r[1] else "No Title"
            print(f"   {r[0]:<12} | € {str(r[2]):<8} | {title_short}")

        # 3. Ultimi Movimenti Prezzi
        print(f"\n{C_YELLOW}💰 ULTIMI MOVIMENTI PREZZI (Price Updater):{C_RESET}")
        moves = get_recent_price_moves(cursor)
        if moves:
            print(f"   {'ORARIO':<10} | {'ASIN':<12} | {'PREZZO':<10} | {'TITOLO'}")
            for m in moves:
                time_str = m[3].strftime("%H:%M")
                title_short = (m[1][:35] + "...") if m[1] else "No Title"
                print(f"   {time_str:<10} | {m[0]:<12} | € {str(m[2]):<8} | {title_short}")
        else:
            print("   (Nessuno storico prezzi ancora disponibile)")

    except Exception as e:
        print(f"{C_RED}❌ Errore Connessione: {e}{C_RESET}")
    finally:
        if conn: conn.close()

def add_asin():
    asin_input = input(f"\n{C_BOLD}Inserisci ASIN (o lista separata da virgola): {C_RESET}").strip()
    asin_input = asin_input.replace("'", "").replace('"', '')
    
    if not asin_input: return

    asins = [x.strip() for x in asin_input.split(',')]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added = 0
    for asin in asins:
        if len(asin) < 5: continue
        try:
            cursor.execute("SELECT id FROM products WHERE asin = %s", (asin,))
            if cursor.fetchone():
                print(f"   ⚠️  {asin} esiste già.")
            else:
                # Rimosso created_at se non esiste, o usato NOW()
                # Se la tua tabella non ha created_at, usa:
                cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", (asin,))
                # Se invece esiste created_at, usa questa riga scommentandola:
                # cursor.execute("INSERT INTO products (asin, status, created_at) VALUES (%s, 'pending', NOW())", (asin,))
                added += 1
                print(f"   ✅ {asin} aggiunto.")
        except Exception as e:
            print(f"   ❌ Errore {asin}: {e}")

    conn.commit()
    conn.close()
    print(f"\n--- Aggiunti {added} ASIN ---")
    time.sleep(1.5)

def reset_status(target_status, label):
    print(f"\n🚑 Reset prodotti '{label}' in corso...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"UPDATE products SET status = 'pending' WHERE status = '{target_status}'")
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            print(f"   ✅ Sbloccati {count} prodotti! Ora sono di nuovo 'Pending'.")
        else:
            print(f"   👍 Nessun prodotto '{label}' trovato.")
            
    except Exception as e:
        print(f"❌ Errore DB: {e}")
    finally:
        conn.close()
    
    input("\nPremi INVIO per tornare al menu...")

def main_loop():
    while True:
        clear_screen()
        show_status()
        print(f"\n{C_BOLD}COMANDI:{C_RESET}")
        print(" [1] ➕ Aggiungi Nuovo ASIN")
        print(" [2] 🔄 Aggiorna Vista")
        print(f" [3] 🚑 Sblocca prodotti {C_YELLOW}'In Lavorazione'{C_RESET} (Bloccati)")
        print(f" [4] ♻️  Riprova prodotti {C_RED}'Failed'{C_RESET} (Errori)")
        print(" [q] 👋 Esci")
        
        choice = input("\nScelta > ").strip().lower()
        
        if choice == '1':
            add_asin()
        elif choice == '2':
            continue
        elif choice == '3':
            reset_status('processing', 'In Lavorazione')
        elif choice == '4':
            reset_status('failed', 'Falliti')
        elif choice == 'q':
            print("Chiusura...")
            break

if __name__ == "__main__":
    main_loop()