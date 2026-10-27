import asyncio
import logging
import aiosqlite
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 📄 Безопасное чтение токена
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        with open("token.txt", "r", encoding="utf-8") as f:
            BOT_TOKEN = f.read().strip()
    except FileNotFoundError:
        print("❌ Ошибка: переменная BOT_TOKEN не задана, и файл token.txt не найден!")
        sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_PATH = "family_notes.db"
WAKE_WORD = "барбос"

user_tags = {}
user_states = {} # {user_id: {'action': 'awaiting_list_item', 'thread_id': 123, 'chat_id': 456}}

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица для списков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS checklists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                thread_id INTEGER,
                item_text TEXT,
                added_by TEXT,
                is_done INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

# --- КЛАВИАТУРЫ ---
def get_main_kb(thread_id):
    # Главное меню (кнопки появляются в зависимости от того, в какой мы теме)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить в список", callback_data="add_item")],
        [InlineKeyboardButton(text="📋 Показать список", callback_data="show_list")],
        [InlineKeyboardButton(text="🗑 Очистить список", callback_data="clear_list")]
    ])

# --- ВЫЗОВ БОТА ---
@dp.message(F.text.lower().contains(WAKE_WORD))
async def wake_up(message: types.Message):
    user_states.pop(message.from_user.id, None)
    caller_tag = user_tags.get(message.from_user.id, message.from_user.first_name)
    
    await message.reply(
        f"Гав! 🐶 Я тут. Что нужно сделать, {caller_tag}?",
        reply_markup=get_main_kb(message.message_thread_id)
    )

# --- УПРАВЛЕНИЕ СПИСКОМ ---
@dp.callback_query(F.data == "add_item")
async def cb_add_item(callback: CallbackQuery):
    # Запоминаем, в какой теме мы находимся
    user_states[callback.from_user.id] = {
        'action': 'awaiting_list_item',
        'thread_id': callback.message.message_thread_id,
        'chat_id': callback.message.chat.id
    }
    
    await callback.message.edit_text(
        "Гав! Напиши, что добавить в список:",
        reply_markup=None
    )
    await callback.answer()

@dp.callback_query(F.data == "show_list")
async def cb_show_list(callback: CallbackQuery):
    thread_id = callback.message.message_thread_id
    async with aiosqlite.connect(DB_PATH) as db:
        if thread_id:
            query = "SELECT id, item_text, is_done FROM checklists WHERE chat_id = ? AND thread_id = ? AND is_done = 0 ORDER BY id ASC"
            params = (callback.message.chat.id, thread_id)
        else:
            query = "SELECT id, item_text, is_done FROM checklists WHERE chat_id = ? AND thread_id IS NULL AND is_done = 0 ORDER BY id ASC"
            params = (callback.message.chat.id,)

        async with db.execute(query, params) as cursor:
            items = await cursor.fetchall()

    if not items:
        await callback.message.edit_text("📭 Список пуст.", reply_markup=get_main_kb(thread_id))
        await callback.answer()
        return

    # Формируем красивый список с кнопками "Готово"
    response = "📝 **Текущий список:**\n\n"
    keyboard = []
    
    for item in items:
        item_id = item[0]
        text = item[1]
        response += f"• {text}\n"
        # Добавляем кнопку для каждого пункта
        keyboard.append([InlineKeyboardButton(text=f"✅ {text}", callback_data=f"done_{item_id}")])

    # Добавляем кнопки навигации
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])

    await callback.message.edit_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("done_"))
async def cb_mark_done(callback: CallbackQuery):
    item_id = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE checklists SET is_done = 1 WHERE id = ?", (item_id,))
        await db.commit()
    
    await callback.answer("✅ Вычеркнуто!")
    # Обновляем список на экране
    await cb_show_list(callback)

@dp.callback_query(F.data == "clear_list")
async def cb_clear_list(callback: CallbackQuery):
    user_states.pop(callback.from_user.id, None)
    thread_id = callback.message.message_thread_id
    
    async with aiosqlite.connect(DB_PATH) as db:
        if thread_id:
            await db.execute("DELETE FROM checklists WHERE chat_id = ? AND thread_id = ?", (callback.message.chat.id, thread_id))
        else:
            await db.execute("DELETE FROM checklists WHERE chat_id = ? AND thread_id IS NULL", (callback.message.chat.id,))
        await db.commit()
        
    await callback.message.edit_text("🗑️ Список полностью очищен.", reply_markup=get_main_kb(thread_id))
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("Что делаем дальше?", reply_markup=get_main_kb(callback.message.message_thread_id))
    await callback.answer()

# --- ОБРАБОТКА ТЕКСТА (ДОБАВЛЕНИЕ ЭЛЕМЕНТА) ---
@dp.message(F.text)
async def handle_text(message: types.Message):
    state = user_states.get(message.from_user.id)
    
    # Если пользователь нажал "Добавить в список" и пишет текст
    if state and state.get('action') == 'awaiting_list_item':
        item_text = message.text
        thread_id = state.get('thread_id')
        user_states.pop(message.from_user.id, None)
        
        author = user_tags.get(message.from_user.id, message.from_user.first_name)
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO checklists (chat_id, thread_id, item_text, added_by) VALUES (?, ?, ?, ?)",
                (message.chat.id, thread_id, item_text, author)
            )
            await db.commit()
        
        await message.reply(
            f"✅ Гав! Добавил в список: _{item_text}_", 
            parse_mode="Markdown",
            reply_markup=get_main_kb(thread_id)
        )
        return

async def main():
    await init_db()
    print(f"Бот запущен! Ждем кодовое слово: '{WAKE_WORD}'")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
