import imaplib
import email
from email.header import decode_header
import requests
import os
import json
import base64
import re
import sys
import time
import shutil
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURAZIONE ---
load_dotenv() 

WP_API_URL = "https://www.recensionedigitale.it/wp-json/wp/v2"
WP_USER = os.getenv('WP_USER') 
WP_APP_PASSWORD = os.getenv('WP_PASSWORD') 

IMAP_SERVER = os.getenv('IMAP_SERVER', 'imaps.aruba.it')
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASS = os.getenv('IMAP_PASSWORD')
IMAP_FOLDER = os.getenv('IMAP_FOLDER', 'Da Pubblicare')

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

TEMP_DIR = "temp_pr_attachments"

def get_auth_header():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode())
    return {'Authorization': f'Basic {token.decode("utf-8")}'}

def clean_string(text):
    if not text: return ""
    return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore')

def decode_mime_words(s):
    if not s: return ""
    return u''.join(word.decode(encoding or 'utf-8') if isinstance(word, bytes) else word for word, encoding in decode_header(s))

def list_all_folders(mail):
    """Diagnostica: Stampa tutte le cartelle disponibili sul server"""
    print("\n--- DIAGNOSI CARTELLE DISPONIBILI ---")
    status, folders = mail.list()
    if status == 'OK':
        for f in folders:
            # Il nome della cartella è solitamente l'ultima parte della stringa restituita
            print(f" > {f.decode('utf-8')}")
    print("-------------------------------------\n")

def get_all_wp_categories():
    categories = {}
    page = 1
    while True:
        try:
            url = f"{WP_API_URL}/categories?per_page=100&page={page}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200: break
            data = r.json()
            if not data: break
            for c in data: categories[c['name']] = c['id']
            page += 1
        except: break
    return categories

# [Le funzioni extract_text_from_file, upload_local_image_to_wp, format_text_to_html, is_valid_press_release, extract_product_name, generate_presentation_content, build_presentation_html rimangono invariate...]

def publish_to_wp(title, content, category_id, custom_slug):
    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'
    payload = {'title': title, 'content': content, 'status': 'draft', 'categories': [category_id], 'slug': custom_slug}
    r = requests.post(f"{WP_API_URL}/posts", headers=headers, json=payload)
    if r.status_code == 201: print(f"   ✅ BOZZA CREATA: {r.json().get('link')}")
    else: print(f"   ❌ ERRORE WP: {r.text}")

def process_emails():
    print(f"🚀 Email Bot Attivo (Python {sys.version.split()[0]})")
    print(f"Tentativo di connessione a {IMAP_SERVER}:993...")
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        print("✅ Autenticazione riuscita.")

        # Tentativo di selezione cartella
        # Usiamo le virgolette per gestire nomi con spazi
        status, messages = mail.select(f'"{IMAP_FOLDER}"')
        
        if status != "OK":
            print(f"❌ Errore: Cartella '{IMAP_FOLDER}' non trovata.")
            list_all_folders(mail)
            print("Cerca nella lista sopra il nome esatto e aggiorna IMAP_FOLDER nel file .env")
            return

        status, data = mail.search(None, 'UNSEEN')
        mail_ids = data[0].split()
        
        if not mail_ids:
            print(f"Nessuna nuova email non letta in '{IMAP_FOLDER}'.")
            return

        cat_list = get_all_wp_categories()
        os.makedirs(TEMP_DIR, exist_ok=True)

        for i in mail_ids:
            # ... [Il resto della logica di elaborazione email rimane identica]
            print(f"Elaborazione email ID {i.decode()}...")
            # (Codice omesso per brevità, usa la logica della versione precedente)

        mail.logout()

    except Exception as e:
        print(f"❌ Errore imprevisto nel bot: {e}")

if __name__ == "__main__":
    process_emails()