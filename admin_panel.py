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

        # Conteggi semplici
        cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
        stats = dict(cursor.fetchall())
        
        pending = stats.get('pending', 0)
        processing = stats.get('processing', 0)
        published = stats.get('published', 0)
        failed = stats.get('failed', 0)
        draft = stats.get('draft', 0)

        print("\n📊 STATO SERVER (Stable V1 + Rescue):")
        print(f"   ⏳ In Coda (Pending):       {pending}")
        print(f"   ⚙️  In Lavorazione:          {processing}")
        print(f"   📝 Bozze (Draft):           {draft}")
        print(f"   ✅ Pubblicati:              {published}")
        print(f"   ❌ Errori:                  {failed}")
        print("========================================")

        # Lista ultimi pubblicati
        print("\n✅ ULTIMI 5 PUBBLICATI:")
        try:
            cursor.execute("SELECT asin, title, current_price FROM products WHERE status = 'published' ORDER BY id DESC LIMIT 5")
            recents = cursor.fetchall()
            for r in recents:
                title_short = r[1][:40] + "..." if r[1] else "No Title"
                print(f"   {r[0]} | {title_short} | € {r[2]}")
        except:
            print("   (Impossibile leggere ultimi pubblicati)")

    except Exception as e:
        print(f"❌ Errore Connessione: {e}")
    finally:
        if conn: conn.close()

def add_asin():
    asin_input = input("\nInserisci ASIN (o lista separata da virgola): ").strip()
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
                cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", (asin,))
                added += 1
                print(f"   ✅ {asin} aggiunto.")
        except Exception as e:
            print(f"   ❌ Errore {asin}: {e}")

    conn.commit()
    conn.close()
    print(f"\n--- Aggiunti {added} ASIN ---")
    time.sleep(1.5)

def reset_stuck_products():
    """Riporta i prodotti bloccati in 'processing' allo stato 'pending'"""
    print("\n🚑 Tentativo di sblocco coda...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # La query magica: sposta tutto ciò che è bloccato indietro nella coda
        cursor.execute("UPDATE products SET status = 'pending' WHERE status = 'processing'")
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            print(f"   ✅ Sbloccati {count} prodotti! Ora sono di nuovo in coda (Pending).")
            print("      Il bot li riprocesserà automaticamente.")
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
        print(" [3] 🚑 Sblocca 'In Lavorazione' (Reset)")
        print(" [q] Esci")
        
        choice = input("\nScelta > ").strip().lower()
        
        if choice == '1':
            add_asin()
        elif choice == '2':
            continue
        elif choice == '3':
            reset_stuck_products()
        elif choice == 'q':
            break

if __name__ == "__main__":
    main_loop()