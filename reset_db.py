import mysql.connector
import os

DB_CONFIG = {
    'user': 'root',
    'password': 'FfEivO8tgJSGWkxEV84g4qIVvmZgspy8lnnS3O4eHiyZdM5vPq9cVg1ZemSDKHZL', # O usa os.getenv se preferisci
    'host': '80.211.135.46',
    'port': 3306,
    'database': 'recensionedigitale'
}

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# CANCELLA TUTTO per ripartire da zero
cursor.execute("DELETE FROM products")
conn.commit()
print("🗑️ Database pulito! Ora il bot riprocesserà tutto come NUOVO.")
