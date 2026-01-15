import requests
import base64
import os

# CONFIGURAZIONE
WP_URL = "https://www.recensionedigitale.it/wp-json/wp/v2/categories"
WP_USER = "davide" # O il tuo user
# INCOLLA QUI LA TUA PASSWORD APPLICAZIONE (quella che usi negli altri script)
WP_APP_PASSWORD = "C3iY 63kW 6vjT gHzp QwcH WIXL" 

def get_cats():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    headers = {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json'
    }

    print("📡 Scarico le categorie da RecensioneDigitale.it...")
    
    # Scarichiamo fino a 100 categorie
    response = requests.get(f"{WP_URL}?per_page=100", headers=headers)
    
    if response.status_code == 200:
        cats = response.json()
        print("\n✅ ECCO LE TUE CATEGORIE:")
        print("Copia e incolla questa lista nella chat con Gemini:\n")
        print("{")
        for c in cats:
            print(f"    '{c['name']}': {c['id']},")
        print("}")
    else:
        print(f"❌ Errore: {response.status_code}")

if __name__ == "__main__":
    get_cats()