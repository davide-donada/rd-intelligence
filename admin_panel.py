import mysql.connector
import os
import time

# --- CONFIGURAZIONE ---
DB_CONFIG = {
    'user': 'root',
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL',
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_status():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Conteggi
    cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
    stats = dict(cursor.fetchall())
    
    pending = stats.get('pending', 0)
    processing = stats.get('processing', 0)
    published = stats.get('published', 0)
    failed = stats.get('failed', 0)
    draft = stats.get('draft', 0)

    print("\n📊 STATO SERVER:")
    print(f"   ⏳ In Coda (Pending):       {pending}")
    print(f"   ⚙️  In Lavorazione (Ora):    {processing}")
    print(f"   📝 Bozze (Draft):           {draft}")
    print(f"   ✅ Pubblicati Totali:       {published}")
    print("========================================")

    # Ultimi Pubblicati
    print("\n✅ ULTIMI 5 PUBBLICATI:")
    cursor.execute("SELECT asin, title, current_price, last_update FROM products WHERE status = 'published' ORDER BY last_update DESC LIMIT 5")
    recents = cursor.fetchall()
    for r in recents:
        asin = r[0]
        title = r[1][:40] + "..." if r[1] else "No Title"
        price = r[2]
        date_str = r[3].strftime("%H:%M") if r[3] else "--:--"
        print(f"   TIME: {date_str} | {asin} | {title} | € {price}")

    # Ultimi Errori
    if failed > 0:
        print(f"\n❌ ULTIMI ERRORI (Totale: {failed}):")
        cursor.execute("SELECT asin FROM products WHERE status = 'failed' ORDER BY id DESC LIMIT 5")
        errors = cursor.fetchall()
        for e in errors:
            print(f"   ASIN: {e[0]}")

    conn.close()

def add_asin():
    asin_input = input("\nInserisci ASIN (o lista separata da virgola): ").strip()
    if not asin_input: return

    asins = [x.strip() for x in asin_input.split(',')]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added = 0
    for asin in asins:
        if len(asin) < 10: continue
        try:
            # Controllo duplicati
            cursor.execute("SELECT id FROM products WHERE asin = %s", (asin,))
            if cursor.fetchone():
                print(f"   ⚠️  {asin} esiste già.")
            else:
                cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", (asin,))
                added += 1
                print(f"   ✅ {asin} aggiunto.")
        except Exception as e:
            print(f"   ❌ Errore {asin}: {e}")

    conn.commit()
    conn.close()
    print(f"\n--- Aggiunti {added} nuovi prodotti ---")
    time.sleep(1.5)

def delete_asin():
    """Permette di cancellare un ASIN specifico o di pulire tutti gli errori"""
    target = input("\n🗑️  Inserisci ASIN da cancellare (oppure scrivi 'failed' per pulire tutti gli errori): ").strip()
    
    if not target: return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if target.lower() == 'failed':
            cursor.execute("DELETE FROM products WHERE status = 'failed'")
            print(f"   🧹 Pulizia completata! Cancellati {cursor.rowcount} prodotti falliti.")
        else:
            cursor.execute("DELETE FROM products WHERE asin = %s", (target,))
            if cursor.rowcount > 0:
                print(f"   🗑️  ASIN {target} eliminato dal database.")
            else:
                print(f"   ⚠️  ASIN {target} non trovato.")
        
        conn.commit()
    except Exception as e:
        print(f"❌ Errore DB: {e}")
    finally:
        conn.close()
    
    input("\nPremi INVIO per tornare al menu...")

def reset_stuck_products():
    """Sblocca i prodotti rimasti in 'processing' per errore"""
    print("\n🚑 Tentativo di sblocco coda...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Riporta tutto ciò che è 'processing' a 'pending'
        cursor.execute("UPDATE products SET status = 'pending' WHERE status = 'processing'")
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            print(f"   ✅ Sbloccati {count} prodotti! Ora sono di nuovo in coda (Pending).")
            print("      Il bot li riprocesserà al prossimo giro.")
        else:
            print("   👍 Nessun prodotto bloccato trovato.")
            
    except Exception as e:
        print(f"❌ Errore DB: {e}")
    finally:
        conn.close()
    
    input("\nPremi INVIO per tornare al menu...")

def main_loop():
    while True:
        clear_screen()
        show_status()
        print("\nCOMANDI:")
        print(" [1] Aggiungi Nuovo ASIN")
        print(" [2] Aggiorna Vista")
        print(" [3] 🗑️  Cancella ASIN (o pulisci errori)")
        print(" [4] 🚑 Sblocca 'In Lavorazione' (Reset)")
        print(" [q] Esci")
        
        choice = input("\nScelta > ").strip().lower()
        
        if choice == '1':
            add_asin()
        elif choice == '2':
            continue
        elif choice == '3':
            delete_asin()
        elif choice == '4':
            reset_stuck_products()
        elif choice == 'q':
            print("Bye Direttore! 👋")
            break

if __name__ == "__main__":
    main_loop()