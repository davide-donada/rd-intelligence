import requests
import re
import urllib.parse

def clean_amazon_title(title):
    """
    Estrae le parole chiave vitali dal titolo Amazon per evitare errori.
    Prende: La prima parola (Marca) + Qualsiasi parola che contiene numeri (Modello).
    """
    words = title.replace("-", " ").replace("/", " ").split()
    
    # 1. La Marca (quasi sempre la prima parola)
    brand = words[0] if words else ""
    
    # 2. Il Modello (parole che contengono almeno un numero)
    # Es: "11090", "S23", "iPhone15", "RX7600"
    model_keywords = [w for w in words if any(char.isdigit() for char in w)]
    
    # Filtriamo numeri inutili (es. "2024", "1080p", "5000mAh" se vogliamo essere perfezionisti, 
    # ma per ora teniamo tutto, meglio un dato in più che uno in meno)
    # Rimuoviamo duplicati mantenendo l'ordine
    seen = set()
    model_keywords = [x for x in model_keywords if not (x in seen or seen.add(x))]

    # Se non abbiamo trovato numeri (es. "Magic Mouse"), usiamo le prime 4 parole come fallback
    if not model_keywords:
        return " ".join(words[:4])
    
    # Costruiamo la query chirurgica: "Cecotec 11090"
    # Aggiungiamo anche la seconda parola del titolo se non contiene numeri, spesso aiuta (es. "Samsung Galaxy")
    secondary = ""
    if len(words) > 1 and not any(char.isdigit() for char in words[1]):
        secondary = words[1]

    query = f"{brand} {secondary} {' '.join(model_keywords)}"
    return query

def find_video_review(product_title):
    """
    Cerca una recensione su YouTube usando la Smart Query.
    """
    
    # 1. Pulizia Intelligente
    smart_query = clean_amazon_title(product_title)
    search_term = f"{smart_query} recensione ita"
    
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
            print(f"     ⚠️ YouTube ha risposto: {response.status_code}")
            return None
            
        html = response.text
        
        # 2. Caccia all'ID con Regex
        # Cerchiamo il primo video ID nei risultati
        video_ids = re.findall(r'"videoId":"(\w{11})"', html)
        
        if video_ids:
            # Prendiamo il primo risultato
            first_video = video_ids[0]
            print(f"     ✅ Trovato video ID: {first_video}")
            return first_video
        else:
            print("     ❌ Nessun video trovato.")
            return None
            
    except Exception as e:
        print(f"     ⚠️ Errore ricerca: {e}")
        return None

if __name__ == "__main__":
    # Testiamo proprio il caso che falliva
    titolo_difficile = "Cecotec Robot Aspirapolvere Lavapavimenti Laser Conga 11090 Spin Revolution Home&Wash"
    print(find_video_review(titolo_difficile))
    
    # Testiamo un classico
    titolo_facile = "Samsung Galaxy S23 Ultra Smartphone Android"
    print(find_video_review(titolo_facile))