import logging
import mysql.connector
import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- CONFIGURAZIONE ---
# 1. Incolla qui il token che ti ha dato @BotFather
TELEGRAM_TOKEN = "1146058895:AAGqUQ89gCUVAvMW7Z8y4mftiTCL6ym2NKQ"

# 2. Inserisci il tuo ID numerico (lo trovi scrivendo a @userinfobot su Telegram)
# Senza questo, chiunque trovi il bot potrebbe cancellarti il database!
ALLOWED_USER_ID = 123456789  

# Configurazione Database (Uguale al monitor)
DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '80.211.135.46'),
    'port': 3306,
    'database': 'recensionedigitale'
}

# Setup Log
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- FUNZIONI DATABASE ---

def get_db_stats():
    """Recupera le statistiche dei prodotti"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
        stats = dict(cursor.fetchall())
        
        msg = "📊 *STATO SISTEMA RD*\n\n"
        msg += f"⏳ Pending (Coda): `{stats.get('pending', 0)}`\n"
        msg += f"⚙️ In Lavorazione: `{stats.get('processing', 0)}`\n"
        msg += f"✅ Pubblicati: `{stats.get('published', 0)}`\n"
        msg += f"❌ Falliti: `{stats.get('failed', 0)}`\n"
        msg += f"🗑️ Cestinati: `{stats.get('trash', 0)}`"
        return msg
    except Exception as e:
        return f"❌ Errore connessione DB: {e}"
    finally:
        if conn: conn.close()

def reset_stuck_products():
    """Sblocca i prodotti rimasti in 'processing' per errore"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET status = 'pending' WHERE status = 'processing'")
        count = cursor.rowcount
        conn.commit()
        return f"🚑 *RESET COMPLETATO*\nHo sbloccato {count} prodotti che erano bloccati in lavorazione."
    except Exception as e:
        return f"❌ Errore Reset: {e}"
    finally:
        if conn: conn.close()

def get_latest_price_changes():
    """Recupera gli ultimi 5 cambi di prezzo"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # Query per prendere gli ultimi 5 record dalla history
        query = """
        SELECT p.asin, ph.price, ph.recorded_at 
        FROM price_history ph 
        JOIN products p ON ph.product_id = p.id 
        ORDER BY ph.recorded_at DESC LIMIT 5
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            return "📭 Nessun cambio prezzo recente."
            
        msg = "💰 *ULTIMI AGGIORNAMENTI*\n\n"
        for asin, price, date in rows:
            # Formatta l'ora
            time_str = date.strftime('%H:%M')
            msg += f"⏰ {time_str} - `{asin}`\n   🏷️ *€ {price}*\n"
        return msg
    except Exception as e:
        return f"❌ Errore History: {e}"
    finally:
        if conn: conn.close()

def add_asin(asin_text):
    """Aggiunge un ASIN al database"""
    clean_asin = asin_text.strip().upper()
    if len(clean_asin) != 10:
        return "⚠️ Errore: Un ASIN deve essere di 10 caratteri."
        
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Controllo duplicati
        cursor.execute("SELECT id FROM products WHERE asin = %s", (clean_asin,))
        if cursor.fetchone():
            return f"⚠️ L'ASIN `{clean_asin}` è già presente nel database."
            
        # Inserimento
        cursor.execute("INSERT INTO products (asin, status) VALUES (%s, 'pending')", (clean_asin,))
        conn.commit()
        return f"✅ ASIN `{clean_asin}` aggiunto alla coda di pubblicazione!"
    except Exception as e:
        return f"❌ Errore SQL: {e}"
    finally:
        if conn: conn.close()

# --- GESTORI TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⛔ Accesso Negato.")
        return

    # Tastiera personalizzata
    keyboard = [
        ['📊 Stato Sistema', '💰 Ultimi Prezzi'],
        ['🚑 Reset Blocchi', '❓ Help']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="👋 *Admin Panel Attivo*\nUsa i tasti sotto o invia un ASIN per aggiungerlo.", 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID: return

    text = update.message.text
    response = ""

    # Router dei comandi
    if text == '📊 Stato Sistema':
        response = get_db_stats()
    elif text == '💰 Ultimi Prezzi':
        response = get_latest_price_changes()
    elif text == '🚑 Reset Blocchi':
        response = reset_stuck_products()
    elif text == '❓ Help':
        response = "💡 *GUIDA RAPIDA*\n\n1. Invia un codice **ASIN** (es. B08ABC1234) per aggiungere un prodotto.\n2. Usa **Stato** per vedere la coda.\n3. Usa **Reset** se vedi troppi prodotti in 'processing' da ore."
    elif len(text) == 10 and text.startswith("B0"):
        # Se sembra un ASIN, prova ad aggiungerlo
        response = add_asin(text)
    else:
        response = "Non ho capito. Usa i tasti o invia un ASIN valido."

    await context.bot.send_message(chat_id=update.effective_chat.id, text=response, parse_mode='Markdown')

# --- AVVIO ---
if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    
    application.add_handler(start_handler)
    application.add_handler(msg_handler)
    
    print("🤖 Bot Admin avviato! Premi Ctrl+C per fermarlo.")
    application.run_polling()