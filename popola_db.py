import mysql.connector
from datetime import datetime

# --- CONFIGURAZIONE ---
DB_CONFIG = {
    'user': 'root',           
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL',  # <--- METTI LA PASSWORD!
    'host': '80.211.135.46',  
    'port': 3306,             
    'database': 'recensionedigitale'  # <--- Aggiornato con il tuo nome
}

def inserisci_prodotto_test():
    print(f"🔌 Mi collego al DB '{DB_CONFIG['database']}' su {DB_CONFIG['host']}...")
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("✅ Connesso con successo!")

        # DATI DI TEST (Simuliamo un prodotto scaricato)
        asin = "B0CLTF2L5P" 
        title = "Apple iPhone 15 (128 GB) - Nero - Test Connessione"
        price = 829.99
        url_img = "https://m.media-amazon.com/images/I/61f4dTush1L._AC_SL1500_.jpg"
        
        # Query "UPSERT" (Inserisci o Aggiorna)
        query = """
        INSERT INTO products (asin, title, current_price, image_url, status)
        VALUES (%s, %s, %s, %s, 'draft')
        ON DUPLICATE KEY UPDATE 
            current_price = VALUES(current_price), 
            title = VALUES(title),
            last_checked = NOW();
        """
        
        cursor.execute(query, (asin, title, price, url_img))
        conn.commit()
        
        print(f"🚀 Query eseguita! Prodotto '{title}' salvato nel database remoto.")

    except mysql.connector.Error as err:
        print(f"❌ Errore MySQL: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("🔒 Connessione chiusa.")

if __name__ == "__main__":
    inserisci_prodotto_test()