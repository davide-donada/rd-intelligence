# ... (Parti iniziali, upload_image e analyze_price uguali) ...

def generate_scorecard_html(score, badge, sub_scores):
    badge_color = "#28a745"
    if score < 7: badge_color = "#ffc107"
    if score < 5: badge_color = "#dc3545"

    bars_html = ""
    for item in sub_scores:
        val = item.get('value', 8)
        label = item.get('label', 'Qualità')
        percent = val * 10
        bars_html += f"""
        <div style="margin-bottom: 10px;">
            <div style="display:flex; justify-content:space-between; font-size:0.9rem; font-weight:600; margin-bottom:5px;">
                <span>{label}</span>
                <span>{val}/10</span>
            </div>
            <div style="background:#eee; border-radius:10px; height:10px; width:100%; overflow:hidden;">
                <div class="rd-bar" style="width:{percent}%; height:100%; background: {badge_color}; border-radius:10px;"></div>
            </div>
        </div>"""

    return f"""
    <div style='background: #fdfdfd; border: 1px solid #eee; border-radius: 12px; padding: 25px; margin: 30px 0;'>
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid #eee; padding-bottom:15px;'>
            <div>
                <span style='background:{badge_color}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; text-transform:uppercase; font-size:0.8rem;'>{badge}</span>
                <h3 style='margin: 10px 0 0 0;'>Verdetto Finale</h3>
            </div>
            <div style='background:{badge_color}1a; color:{badge_color}; width:60px; height:60px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.5rem; font-weight:bold; border: 2px solid {badge_color};'>{score}</div>
        </div>
        {bars_html}
    </div>"""

def format_article_html(product, local_image_url=None, ai_data=None):
    # ... (header e price_widget come prima) ...
    
    score = ai_data.get('final_score', 8.0)
    badge = ai_data.get('verdict_badge', 'Consigliato')
    sub_scores = ai_data.get('sub_scores', [])
    
    scorecard_html = generate_scorecard_html(score, badge, sub_scores)
    
    # Uniamo tutto: Header + Testo AI + Box Voti + Video + Footer
    return header_html + ai_data.get('html_content', '') + scorecard_html + video_html + footer_html