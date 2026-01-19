import requests
import re
import urllib.parse

def clean_amazon_title(title):
    """
    Costruisce una query YouTube a prova di bomba.
    Logica:
    1. Prende le prime 6 parole (per catturare "Mambo", "Conga", "Galaxy").
    2. Cerca nel resto del titolo codici modello (es. "11090").
    3. Scarta unità di misura che confondono (es. "1600W").
    """
    # Pulizia base caratteri
    clean_t = title.replace("-", " ").replace("/", " ").replace(",", " ").replace("|", " ")
    words = clean_t.split()
    
    if not words: return ""

    # 1. LA TESTA: Le prime 6 parole sono sacre.
    # Includono Marca + Famiglia Prodotto (es. "Cecotec Robot Cucina Multifunzione Mambo")
    head_words = words[:6]
    
    # 2. LA CODA: Cerchiamo numeri nel resto del titolo
    tail_numbers = []
    
    # Unità di misura da ignorare se attaccate a un numero
    ignored_units = ['w', 'v', 'hz', 'mah', 'gr', 'kg', 'ml', 'l', 'pack', 'pz']
    
    for w in words[6:]:
        # Se la parola contiene un numero
        if any(char.isdigit() for char in w):
            w_lower = w.lower()
            
            # Controllo se è un'unità di misura (es. 1600W finisce con 'w')
            is_unit = False
            for unit in ignored_units:
                if w_lower.endswith(unit) and len(w_lower) > len(unit):
                    # Controllo semplice: se tolgo l'unità resta un numero? (es. 1600W -> 1600)
                    part_without_unit = w_lower.replace(unit, "")
                    if part_without_unit.isdigit():
                        is_unit = True
                        break
            
            # Se NON è un'unità di misura (o se è un codice misto tipo S23), lo teniamo
            if not is_unit:
                tail_numbers.append(w)

    # 3. UNIONE
    # Uniamo Testa + Numeri trovati
    query_words = head_words + tail_numbers
    
    # Limitiamo a 10 parole totali per non far impazzire YouTube
    final_query = " ".join(query_words[:10])
    
    return final_query

def find_video_review(product_title):
    """
    Cerca una recensione su YouTube usando la logica 'Head + Tail'.
    """
    
    # 1. Genera Query Intelligente
    smart_query = clean_amazon_title(product_title)
    search_term = f"{smart_query} recensione ita"
    
    # Codifica URL
    query_string = urllib.parse.quote(search_term)
    url = f"https://www.youtube.com/results?search_query={query_string}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    print(f"   🎥 Cerco su YouTube: '{search_term}'...")
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"     ⚠️ YouTube Status: {response.status_code}")
            return None
            
        html = response.text
        
        # 2. Regex per trovare ID video
        video_ids = re.findall(r'"videoId":"(\w{11})"', html)
        
        if video_ids:
            print(f"     ✅ Trovato video ID: {video_ids[0]}")
            return video_ids[0]
        else:
            print("     ❌ Nessun video trovato.")
            return None
            
    except Exception as e:
        print(f"     ⚠️ Errore: {e}")
        return None

if __name__ == "__main__":
    # TEST CRITICO: Il tuo caso specifico
    mambo = "Cecotec Robot di Cucina Multifunzione Mambo 11090, 1600 W, 37 Funzioni"
    print(f"\nTEST MAMBO (Cucina): {find_video_review(mambo)}")
    
    # TEST CONGA (Aspirapolvere)
    conga = "Cecotec Robot Aspirapolvere Lavapavimenti Laser Conga 11090 Spin Revolution"
    print(f"\nTEST CONGA (Pulizia): {find_video_review(conga)}")