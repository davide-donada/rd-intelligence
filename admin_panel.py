import mysql.connector
import os
import time
from datetime import datetime

# --- CONFIGURAZIONE DATABASE ---
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD', 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

C_RESET, C_RED, C_GREEN, C_YELLOW, C_BLUE, C_CYAN, C_BOLD = "\033[0m", "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[96m", "\033[1m"

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_status():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Statistiche (Senza created_at)
        cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
        stats = dict(cursor.fetchall())
        
        print(f"\n{C_BOLD}{C_CYAN}📊 DASHBOARD RD (v2.4){C_RESET}")
        print(f"   ⏳ Pending: {C_CYAN}{stats.get('pending',0)}{C_RESET} | ⚙️  Work: {C_YELLOW}{stats.get('processing',0)}{C_RESET} | ✅ Pub: {C_GREEN}{stats.get('published',0)}{C_RESET} | ❌ Fail: {C_RED}{stats.get('failed',0)}{C_RESET}")
        print("─" * 65)

        # 2. Ultimi Pubblicati (Ordiniamo per ID invece che data)
        print(f"\n{C_GREEN}✅ ULTIMI PUBBLICATI:{C_RESET}")
        cursor.execute("SELECT asin, title, current_price FROM products WHERE status = 'published' ORDER BY id DESC LIMIT 5")
        for r in cursor.fetchall():
            title = (r[1][:45] + "...") if r[1] else "Titolo non disponibile"
            print(f"   {r[0]:<12} | € {str(r[2]):<7} | {title}")

        # 3. Storico Prezzi (Qui usiamo h.recorded_at che esiste nella tabella price_history)
        print(f"\n{C_YELLOW}💰 ULTIMI CAMBI PREZZO:{C_RESET}")
        cursor.execute("""
            SELECT p.asin, h.price, h.recorded_at 
            FROM price_history h 
            JOIN products p ON h.product_id = p.id 
            ORDER BY h.recorded_at DESC LIMIT 5
        """)
        for m in cursor.fetchall():
            print(f"   {m[2].strftime('%H:%M')} | {m[0]:<12} | € {str(m[1]):<7}")

    except Exception as e:
        print(f"{C_RED}❌ Errore: {e}{C_RESET}")
    finally:
        if conn: conn.close()

def add_asin():
    print(f"\n{C_BOLD}➕ AGGIUNGI ASIN{C_RESET}")
    asin_input = input("Inserisci ASIN (separati da virgola): ").strip().upper()
    if not asin_input: return

    asins = [x.strip() for x in asin_input.replace("'", "").split(',')]
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for asin in asins:
        try:
            cursor.execute("SELECT id FROM products WHERE asin = %s", (asin,))
            if cursor.fetchone():
                print(f"   ⚠️  {asin} già presente.")
            else:
                # RIMOSSO created_at dalla query
                cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", (asin,))
                print(f"   ✅ {asin} in coda.")
        except Exception as e: print(f"   ❌ Errore {asin}: {e}")

    conn.commit()
    conn.close()
    time.sleep(1)

def reset_status(target_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE products SET status = 'pending' WHERE status = '{target_status}'")
    print(f"   ✅ {cursor.rowcount} prodotti resettati.")
    conn.commit()
    conn.close()
    time.sleep(1)

def main():
    while True:
        clear_screen()
        show_status()
        print(f"\n{C_BOLD}COMANDI:{C_RESET} [1] Aggiungi | [2] Refresh | [3] Reset Lavorazione | [4] Reset Falliti | [Q] Esci")
        choice = input("\n> ").strip().lower()
        if choice == '1': add_asin()
        elif choice == '3': reset_status('processing')
        elif choice == '4': reset_status('failed')
        elif choice == 'q': break

if __name__ == "__main__":
    main()