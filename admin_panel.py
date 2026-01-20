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
    conn = None
    try:
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

        # Ultimi Pubblicati (Con controllo last_update)
        print("\n✅ ULTIMI 5 PUBBLICATI:")
        try:
            cursor.execute("SELECT asin, title, current_price, last_update FROM products WHERE status = 'published' ORDER BY last_update DESC LIMIT 5")
            recents = cursor.fetchall()
            for r in recents:
                asin = r[0]
                title = r[1][:40] + "..." if r[1] else "No Title"
                price = r[2]
                date_str = r[3].strftime("%H:%M") if r[3] else "--:--"
                print(f"   TIME: {date_str} | {asin} | {title} | € {price}")
        except:
            print("   (Nessun dato recente o colonna mancante)")

        # Ultimi Errori
        if failed > 0:
            print(f"\n❌ ULTIMI ERRORI (Totale: {failed}):")
            cursor.execute("SELECT asin FROM products WHERE status = 'failed' ORDER BY id DESC LIMIT 5")
            errors = cursor.fetchall()
            for e in errors:
                print(f"   ASIN: {e[0]}")

    except Exception as e:
        print(f"❌ Errore Connessione Dashboard: {e}")
    finally:
        if conn: conn.close()

def add_asin():
    asin_input = input("\nInserisci ASIN (o lista separata da virgola): ").strip()
    # Pulisce eventuali apici inseriti per sbaglio
    asin_input = asin_input.replace("'", "").replace('"', '')
    
    if not asin_input: return

    asins = [x.strip() for x in asin_input.split(',')]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added = 0
    for asin in asins:
        if len(asin) < 5: continue # ASIN troppo corto, ignora
        try:
            cursor.execute("SELECT id FROM products WHERE asin = %s", [asin])
            if cursor.fetchone():
                print(f"   ⚠️  {asin} esiste già.")
            else:
                cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", [asin])
                added += 1
                print(f"   ✅ {asin} aggiunto.")
        except Exception as e:
            print(f"   ❌ Errore {asin}: {e}")

    conn.commit()
    conn.close()
    print(f"\n--- Aggiunti {added} nuovi prodotti ---")
    time.sleep(1.5)

def delete_asin():
    target = input("\n🗑️  Inserisci ASIN da cancellare (o 'failed'): ").strip()
    # Pulizia input (Anti-Errore Python 'str')
    target = target.replace("'", "").replace('"', '')
    
    if not target: return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if target.lower() == 'failed':
            cursor.execute("DELETE FROM products WHERE status = 'failed'")
            print(f"   🧹 Pulizia completata! Cancellati {cursor.rowcount} prodotti falliti.")
        else:
            # Uso le parentesi quadre [] per passare il parametro come lista, è più sicuro
            cursor.execute("DELETE FROM products WHERE asin = %s", [target])
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
    print("\n🚑 Tentativo di sblocco coda...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE products SET status = 'pending' WHERE status = 'processing'")
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            print(f"   ✅ Sbloccati {count} prodotti! Ora sono di nuovo in coda.")
        else:
            print("   👍 Nessun prodotto bloccato.")
            
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