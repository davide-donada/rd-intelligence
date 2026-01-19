import requests
import re
import urllib.parse

def find_video_review(product_title):
    """
    Cerca una recensione su YouTube analizzando direttamente l'HTML.
    Zero librerie esterne instabili.
    """
    
    # 1. Pulizia e Preparazione Query
    # Prendiamo le prime 5-6 parole per non confondere YouTube con titoli Amazon chilometrici
    clean_title = " ".join(product_title.split()[:6])
    query_string = urllib.parse.quote(f"{clean_title} recensione ita")
    url = f"https://www.youtube.com/results?search_query={query_string}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    print(f"   🎥 Cerco su YouTube: '{clean_title} recensione ita'...")
    
    try:
        # 2. Scarica la pagina dei risultati
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"     ⚠️ YouTube ha risposto: {response.status_code}")
            return None
            
        html = response.text
        
        # 3. Caccia all'ID con Regex (Espressioni Regolari)
        # Cerchiamo il pattern "videoId":"qualcosa" dentro il codice sorgente
        video_ids = re.findall(r'"videoId":"(\w{11})"', html)
        
        if video_ids:
            # Il primo risultato è solitamente il più pertinente
            first_video = video_ids[0]
            print(f"     ✅ Trovato video ID: {first_video}")
            return first_video
        else:
            print("     ❌ Nessun video trovato (Pattern non matchato).")
            return None
            
    except Exception as e:
        print(f"     ⚠️ Errore ricerca nativa: {e}")
        return None

# Test rapido se lanci il file da solo
if __name__ == "__main__":
    # Testiamo con un prodotto reale
    print(find_video_review("iPhone 15 Pro Max 256GB Titanio Naturale"))