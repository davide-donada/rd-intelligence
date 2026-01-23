#!/bin/bash

# Avvia il Bot Telegram in background (con la & finale)
python telegram_admin.py &

# Avvia il Monitor Prezzi in primo piano
python price_updater.py