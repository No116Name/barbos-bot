import asyncio
import logging
import aiosqlite
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 📄 Безопасное чтение токена
# Сначала ищем в переменных окружения (для хостинга),
# Если нет — читаем из файла token.txt (для локального запуска в Termux)
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

def get_main_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить заметку", callback_data="add_note")],
        [InlineKeyboardButton(text="📋 Все заметки", callback_data="list_notes")],
        [InlineKeyboardButton(text="🗑 Очистить всё", callback_data="clear_notes")]
    ])

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                author_tag TEXT,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

user_states = {}

@dp.message(Command("set_tag"))
async def set_tag(message: types.Message):
    if not message.reply_to_message:
        await message.reply("⚠️ Чтобы назначить тег, ответьте этой командой на любое сообщение нужного человека.\nПример: `/set_tag Красавчик`")
        return
    
    target_user = message.reply_to_message.from_user
    tag = message.text.replace("/set_tag", "").strip()
    
    if not tag:
        await message.reply("⚠️ Напиши тег после команды. Например: `/set_tag Красавчик`")
        return

    user_tags[target_user.id] = tag
    await message.reply(f"✅ Отлично! Теперь пользователь **{target_user.first_name}** в заметках будет подписан как **{tag}**.", parse_mode="Markdown")

@dp.message(F.text.lower().contains(WAKE_WORD))
async def wake_up(message: types.Message):
    user_states.pop(message.from_user.id, None)
    caller_tag = user_tags.get(message.from_user.id, message.from_user.first_name)
    
    await message.reply(
        f"Гав! 🐶 Я тут. Что нужно сделать, {caller_tag}?",
        reply_markup=get_main_inline_kb()
    )

@dp.callback_query(F.data == "add_note")
async def cb_add_note(callback: CallbackQuery):
    user_states[callback.from_user.id] = {'action': 'awaiting_text'}
    caller_tag = user_tags.get(callback.from_user.id, callback.from_user.first_name)
    await callback.message.edit_text(
        f"Гав! {caller_tag}, напиши текст заметки одним сообщением в чат:",
        reply_markup=None
    )
    await callback.answer()

@dp.callback_query(F.data == "list_notes")
async def cb_list_notes(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT author_tag, text FROM notes WHERE chat_id = ? ORDER BY id DESC", (callback.message.chat.id,)) as cursor:
            notes = await cursor.fetchall()

    if not notes:
        await callback.message.edit_text("📭 Заметок пока нет.", reply_markup=get_main_inline_kb())
        await callback.answer()
        return

    response = "📝 **Список заметок:**\n\n"
    for note in notes:
        response += f"• {note[1]} _(от {note[0]})_\n\n"

    if len(response) > 4000:
        response = response[:4000] + "\n\n... (обрезано)"

    await callback.message.edit_text(response, parse_mode="Markdown", reply_markup=get_main_inline_kb())
    await callback.answer()

@dp.callback_query(F.data == "clear_notes")
async def cb_clear_notes(callback: CallbackQuery):
    user_states.pop(callback.from_user.id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM notes WHERE chat_id = ?", (callback.message.chat.id,))
        await db.commit()
    await callback.message.edit_text("🗑️ Все заметки удалены.", reply_markup=get_main_inline_kb())
    await callback.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    state = user_states.get(message.from_user.id)
    
    if state and state.get('action') == 'awaiting_text':
        note_text = message.text
        user_states.pop(message.from_user.id, None)
        
        author_tag = user_tags.get(message.from_user.id, message.from_user.first_name)
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO notes (chat_id, author_tag, text) VALUES (?, ?, ?)",
                (message.chat.id, author_tag, note_text)
            )
            await db.commit()
        
        await message.reply(
            f"✅ Гав! Заметка сохранена:\n_{note_text}_", 
            parse_mode="Markdown",
            reply_markup=get_main_inline_kb()
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
