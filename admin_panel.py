import mysql.connector
import os

# --- CONFIGURAZIONE ---
# Usa le stesse credenziali che hai negli altri script o scrivile qui
DB_CONFIG = {
    'user': 'root',
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL', # <--- Sostituisci o usa os.getenv('DB_PASSWORD')
    'host': '80.211.135.46',
    'port': 3306,
    'database': 'recensionedigitale'
}

def get_stats(cursor):
    """Mostra quanti lavori ci sono in coda"""
    cursor.execute("SELECT status, COUNT(*) FROM hunting_list GROUP BY status")
    results = cursor.fetchall()
    print("\n📊 STATO DEL SERVER:")
    if not results:
        print("   (Coda vuota)")
    for status, count in results:
        icon = "⏳" if status == 'pending' else "⚙️" if status == 'processing' else "✅" if status == 'done' else "❌"
        print(f"   {icon} {status.upper()}: {count}")
    print("-" * 30)

def add_asins(conn, cursor):
    print("\n🚀 INSERIMENTO RAPIDO")
    print("Incolla un ASIN (es. B0CLTF2L5P) o una lista separata da virgole/spazi.")
    print("Scrivi 'exit' per uscire.")
    
    while True:
        user_input = input("\n👉 Inserisci ASIN: ").strip()
        
        if user_input.lower() in ['exit', 'quit', 'esci']:
            break
        
        if not user_input:
            continue

        # Pulizia input: gestisce virgole, spazi, invii
        raw_asins = user_input.replace(',', ' ').split()
        
        added_count = 0
        for asin in raw_asins:
            asin = asin.strip()
            if len(asin) < 10: # Controllo base lunghezza ASIN
                print(f"   ⚠️ '{asin}' sembra troppo corto, salto.")
                continue

            try:
                # Inseriamo ignorando i duplicati
                cursor.execute("INSERT IGNORE INTO hunting_list (asin) VALUES (%s)", (asin,))
                if cursor.rowcount > 0:
                    print(f"   ✅ Aggiunto: {asin}")
                    added_count += 1
                else:
                    print(f"   💤 Già presente: {asin}")
            except Exception as e:
                print(f"   ❌ Errore su {asin}: {e}")
        
        conn.commit()
        if added_count > 0:
            print(f"✨ Caricati {added_count} nuovi prodotti in coda!")
            get_stats(cursor)

def main():
    print("🔌 Connessione al Quartier Generale...")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        get_stats(cursor)
        add_asins(conn, cursor)
        
    except mysql.connector.Error as err:
        print(f"❌ Errore di connessione: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("\n👋 Connessione chiusa.")

if __name__ == "__main__":
    main()