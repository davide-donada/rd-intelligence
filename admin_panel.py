import mysql.connector
import os
import sys

# CONFIGURAZIONE (Assicurati che sia uguale agli altri script)
DB_CONFIG = {
    'user': 'root',
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL', # O inserisci la password tra virgolette
    'host': '80.211.135.46',
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Errore di connessione al DB: {e}")
        return None

def show_stats():
    conn = get_db_connection()
    if not conn: return

    cursor = conn.cursor()
    
    # Conta Pending
    cursor.execute("SELECT COUNT(*) FROM hunting_list WHERE status='pending'")
    pending = cursor.fetchone()[0]
    
    # Conta Processing
    cursor.execute("SELECT COUNT(*) FROM hunting_list WHERE status='processing'")
    processing = cursor.fetchone()[0]

    print("\n" + "="*40)
    print(f"📊 STATO SERVER:")
    print(f"   ⏳ In Coda (Pending):      {pending}")
    print(f"   ⚙️  In Lavorazione (Ora):   {processing}")
    print("="*40)
    conn.close()

def show_latest_published():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    
    print("\n✅ ULTIMI 5 PUBBLICATI:")
    # Prende gli ultimi 5 con status 'published'
    cursor.execute("SELECT asin, title, current_price, last_checked FROM products WHERE status='published' ORDER BY last_checked DESC LIMIT 5")
    rows = cursor.fetchall()
    
    if not rows:
        print("   (Nessun articolo pubblicato)")
    else:
        for r in rows:
            titolo = r[1][:40] + "..." if len(r[1]) > 40 else r[1]
            print(f"   DATE: {r[3].strftime('%H:%M')} | {r[0]} | {titolo} | € {r[2]}")
    conn.close()

def show_errors():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    
    cursor.execute("SELECT asin, status FROM hunting_list WHERE status='error' ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    
    if rows:
        print("\n❌ ULTIMI ERRORI (Verifica questi ASIN):")
        for r in rows:
            print(f"   ASIN: {r[0]}")
    conn.close()

def add_asin():
    asin = input("\n📝 Inserisci ASIN (o 'q' per uscire): ").strip()
    if asin.lower() == 'q' or asin == "": return

    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    
    try:
        # Controlla se esiste già
        cursor.execute("SELECT status FROM hunting_list WHERE asin = %s", (asin,))
        exists = cursor.fetchone()
        
        if exists:
            print(f"⚠️  ASIN {asin} è già in lista (Stato: {exists[0]}).")
        else:
            cursor.execute("INSERT INTO hunting_list (asin, status) VALUES (%s, 'pending')", (asin,))
            conn.commit()
            print(f"✅ ASIN {asin} aggiunto alla coda!")
    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        conn.close()

def main_menu():
    while True:
        # Pulisce schermo (opzionale, rimuovi se dà problemi su Windows)
        # os.system('cls' if os.name == 'nt' else 'clear') 
        
        show_stats()
        show_latest_published()
        show_errors()
        
        print("\nCOMMANDI:")
        print(" [1] Aggiungi Nuovo ASIN")
        print(" [2] Aggiorna Vista")
        print(" [q] Esci")
        
        scelta = input("\n👉 Scelta: ").strip().lower()
        
        if scelta == '1':
            add_asin()
        elif scelta == '2':
            continue # Ricarica il loop e quindi le statistiche
        elif scelta == 'q':
            print("👋 Ciao Direttore.")
            break
        else:
            print("Comando non valido.")

if __name__ == "__main__":
    print("🖥️  RECENSIONE DIGITALE - CONTROL TOWER v2")
    main_menu()