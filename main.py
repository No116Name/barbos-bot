import os
import threading
from flask import Flask
import asyncio
import sys

# Импортируем компоненты бота
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bot import dp, bot, init_db

app = Flask(__name__)

@app.route('/')
def health():
    return "Fazafam bot is alive!"

def run_flask():
    # Render передает порт в переменной окружения PORT
    port = int(os.environ.get("PORT", 8080))
    # Отключаем лишние логи Flask, чтобы не засорять консоль
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)

async def main():
    # 1. Инициализируем базу данных
    await init_db()
    print("Бот запущен! Ждем кодовое слово: 'барбос'")
    # 2. Запускаем бота (он займет главный поток)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask в фоновом потоке (чтобы Render видел порт)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота в главном потоке (чтобы asyncio не падал)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
