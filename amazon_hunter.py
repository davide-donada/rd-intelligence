import requests
from bs4 import BeautifulSoup
import mysql.connector
import random
import os

DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15"
]

def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/"
    }
    
    print(f"🕵️‍♂️  Analizzo ASIN: {asin}...")
    try:
        session = requests.Session()
        response = session.get(url, headers=headers)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.content, "lxml")
        
        # TITOLO
        title_tag = soup.find("span", {"id": "productTitle"})
        if not title_tag: return {"asin": asin, "title": "Titolo non trovato", "price": 0, "image": ""}
        title = title_tag.get_text(strip=True)

        # PREZZO
        price = 0.00
        selectors = ['span.a-price.priceToPay span.a-offscreen', '#corePrice_feature_div span.a-price span.a-offscreen']
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                try:
                    price = float(el.get_text(strip=True).replace("€", "").replace(".", "").replace(",", ".").strip())
                    break
                except: pass

        # IMMAGINE
        img_url = ""
        img_tag = soup.find("img", {"id": "landingImage"})
        if img_tag:
            img_url = img_tag.get("src")

        return {"asin": asin, "title": title, "price": price, "image": img_url}
    except Exception as e:
        print(f"❌ Errore scraping: {e}")
        return None

def save_to_db(data):
    if not data: return
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        ai_content = data.get('ai_content', '')
        cat_id = data.get('category_id', 9) # Default Tecnologia se manca

        # Query aggiornata con category_id
        query = """
        INSERT INTO products (asin, title, current_price, image_url, ai_sentiment, category_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'draft')
        ON DUPLICATE KEY UPDATE 
            current_price = VALUES(current_price), 
            title = VALUES(title),
            image_url = VALUES(image_url),
            ai_sentiment = VALUES(ai_sentiment),
            category_id = VALUES(category_id),
            last_checked = NOW();
        """
        cursor.execute(query, (data['asin'], data['title'], data['price'], data['image'], ai_content, cat_id))
        conn.commit()
        print(f"💾 Salvato nel DB (Cat ID: {cat_id})!")
    except Exception as err:
        print(f"❌ Errore DB: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()