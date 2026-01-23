def get_amazon_data(asin):
    url = f"https://www.amazon.it/dp/{asin}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }

    try:
        resp = browser_requests.get(
            url, 
            headers=headers, 
            timeout=30, 
            impersonate="chrome120"
        )
        
        if resp.status_code == 503:
            log(f"      ⚠️  Amazon 503 (Busy) per {asin}")
            return None, None
        
        if resp.status_code != 200: 
            log(f"      ⚠️  Status Code non valido: {resp.status_code} per {asin}")
            return None, None
            
        soup = BeautifulSoup(resp.content, "lxml")
        
        # Check Anti-Bot/Captcha
        page_text = soup.get_text().lower()
        if "inserisci i caratteri" in page_text or "enter the characters" in page_text:
            log(f"      🤖  CAPTCHA rilevato per {asin}")
            return None, None

        # --- FIX IMPORTANTE: ISOLIAMO L'AREA PRODOTTO ---
        # Cerchiamo solo dentro '#centerCol' (Desktop) o '#ppd' (Mobile/Tablet)
        # Questo evita di leggere i prezzi degli "Sponsorizzati" o "Chi ha comprato questo..."
        product_area = soup.select_one('#centerCol') or soup.select_one('#ppd') or soup.select_one('#apex_desktop')
        
        # Se non trova l'area specifica, usa tutta la pagina (fallback rischioso ma necessario)
        search_area = product_area if product_area else soup

        # Cerchiamo il prezzo specificamente nel blocco "Core Price"
        price_el = search_area.select_one('#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen')
        
        # Fallback 1: Blocco generico feature_div
        if not price_el:
            price_el = search_area.select_one('#corePrice_feature_div span.a-price span.a-offscreen')
            
        # Fallback 2: Qualsiasi prezzo nell'area prodotto (escluso header/footer)
        if not price_el:
            price_el = search_area.select_one('span.a-price span.a-offscreen')

        # Pulizia prezzo
        if price_el:
            raw_price = price_el.get_text().strip()
            # Rimuoviamo valuta e formattiamo
            clean_price = raw_price.replace("€", "").replace(".", "").replace(",", ".").strip()
            try:
                price_val = float(clean_price)
            except ValueError:
                log(f"      ⚠️  Errore conversione prezzo: '{raw_price}' per {asin}")
                price_val = None
        else:
            price_val = None
        
        # Deal Detection (cerca solo nell'area prodotto)
        deal_type = None
        badge_area = search_area.select_one('#apex_desktop, .a-section.a-spacing-none.a-spacing-top-mini')
        badge_text = badge_area.get_text().lower() if badge_area else ""

        if "offerta a tempo" in badge_text: deal_type = "⚡ Offerta a Tempo"
        elif "black friday" in badge_text: deal_type = "🖤 Offerta Black Friday"
        elif "prime day" in badge_text: deal_type = "🔵 Offerta Prime Day"
        
        return price_val, deal_type

    except Exception as e: 
        log(f"      ❌ Errore interno Amazon: {e}")
        return None, None