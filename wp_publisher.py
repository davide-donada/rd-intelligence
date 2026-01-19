# ... (Import e Configurazione uguali a prima) ...
# Assicurati di mantenere tutte le funzioni precedenti (upload_image, generate_scorecard, generate_faq)
# Qui modifico solo 'format_article_html' per aggiungere il video.

def format_article_html(product, local_image_url=None, ai_data=None):
    asin = product[1]
    title = product[2]
    price = product[3]
    amazon_image_url = product[5]
    
    # Estrazione Dati
    html_body = ai_data.get('html_content', product[6]) if ai_data else product[6]
    score = ai_data.get('final_score', 8.0) if ai_data else 8.0
    badge = ai_data.get('verdict_badge', 'Consigliato') if ai_data else 'Consigliato'
    sub_scores = ai_data.get('sub_scores', [{'label':'Qualità', 'value':8}]) if ai_data else [{'label':'Qualità', 'value':8}]
    faqs = ai_data.get('faqs', []) if ai_data else []
    
    # NUOVO: Estrazione Video ID 🎥
    video_id = ai_data.get('video_id', None) if ai_data else None

    final_image = local_image_url if local_image_url else amazon_image_url
    aff_link = f"https://www.amazon.it/dp/{asin}?tag=recensionedigitale-21"

    # Header
    header_html = f"""
    <div style="background-color: #fff; border: 1px solid #e1e1e1; padding: 20px; margin-bottom: 30px; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
        <div style="flex: 1; text-align: center; min-width: 200px;">
            <a href="{aff_link}" rel="nofollow sponsored" target="_blank">
                <img src="{final_image}" alt="{title}" style="max-height: 250px; width: auto; object-fit: contain;">
            </a>
        </div>
        <div style="flex: 1.5; min-width: 250px;">
            <h2 style="margin-top: 0; font-size: 1.4rem;">{title}</h2>
            <div class="rd-price-box" style="font-size: 2rem; color: #B12704; font-weight: bold; margin: 10px 0;">€ <span class="rd-price-val">{price}</span></div>
            <a href="{aff_link}" rel="nofollow sponsored" target="_blank" 
               style="background-color: #ff9900; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
               👉 Vedi Offerta su Amazon
            </a>
            <p style="font-size: 0.8rem; color: #666; margin-top: 5px;">Prezzo aggiornato al: <span class="rd-date-val">{datetime.now().strftime("%d/%m/%Y")}</span></p>
        </div>
    </div>
    """

    # Generazione Blocchi
    scorecard_html = generate_scorecard_html(score, badge, sub_scores)
    faq_html, faq_schema = generate_faq_html(faqs)
    
    # NUOVO: Blocco Video 🎥
    video_html = ""
    if video_id:
        video_html = f"""
        <div style="margin: 40px 0;">
            <h3>🎥 Video Recensione Selezionata</h3>
            <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                <iframe src="https://www.youtube.com/embed/{video_id}" 
                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" 
                        frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen>
                </iframe>
            </div>
            <p style="font-size: 0.8rem; color: #777; margin-top: 5px; text-align: center;">Video credit: Canale YouTube selezionato (tutti i diritti appartengono ai creatori)</p>
        </div>
        """
    
    footer_html = """<hr style="margin: 40px 0;"><p style="font-size: 0.75rem; color: #999; text-align: center;">RecensioneDigitale.it partecipa al Programma Affiliazione Amazon EU.</p>"""
    
    # ASSEMBLEA COMPLETA
    return header_html + html_body + scorecard_html + video_html + faq_html + footer_html + faq_schema

# ... (Il resto di run_publisher rimane UGUALE) ...