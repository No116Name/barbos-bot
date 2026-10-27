import os
import threading
from flask import Flask
import asyncio
import sys

# Импортируем твоего бота
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bot import dp, bot

app = Flask(__name__)

@app.route('/')
def health():
    return "Барбос жив и работает!"

def run_bot():
    # Запускаем бота в фоновом потоке
    asyncio.run(dp.start_polling(bot))

# Запускаем бота при старте сервера
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    # Render требует, чтобы мы слушали порт, который он дает
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
