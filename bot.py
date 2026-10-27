import asyncio
import logging
import aiosqlite
import os
import sys
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 📄 Чтение токена
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        with open("token.txt", "r", encoding="utf-8") as f:
            BOT_TOKEN = f.read().strip()
    except FileNotFoundError:
        print("❌ Ошибка: нет BOT_TOKEN!")
        sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_PATH = "family_notes.db"
WAKE_WORD = "барбос"

user_tags = {}
user_states = {}

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                thread_id INTEGER,
                user_id INTEGER,
                text TEXT,
                remind_time TIMESTAMP
            )
        """)
        await db.commit()

# --- МЕНЮ ---
def get_main_kb(thread_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Списки", callback_data="menu_lists")],
        [InlineKeyboardButton(text="⏰ Напоминание", callback_data="add_reminder")],
        [InlineKeyboardButton(text="🎲 Кто моет посуду?", callback_data="random_chore")],
        [InlineKeyboardButton(text="💌 Комплимент", callback_data="compliment")]
    ])

def get_list_kb(thread_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить в список", callback_data="add_item")],
        [InlineKeyboardButton(text="📋 Показать список", callback_data="show_list")],
        [InlineKeyboardButton(text="🗑 Очистить список", callback_data="clear_list")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
    ])

# --- ВЫЗОВ БОТА ---
@dp.message(F.text.lower().contains(WAKE_WORD))
async def wake_up(message: types.Message):
    user_states.pop(message.from_user.id, None)
    caller_tag = user_tags.get(message.from_user.id) or message.from_user.first_name or "друг"
    await message.answer(
        f"Гав! 🐶 Я тут. Чего изволите, {caller_tag}?",
        message_thread_id=message.message_thread_id,
        reply_markup=get_main_kb(message.message_thread_id)
    )

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("Что делаем дальше?", reply_markup=get_main_kb(callback.message.message_thread_id))
    await callback.answer()

@dp.callback_query(F.data == "menu_lists")
async def cb_menu_lists(callback: CallbackQuery):
    await callback.message.edit_text("Управление списками:", reply_markup=get_list_kb(callback.message.message_thread_id))
    await callback.answer()

# --- СПИСКИ ---
@dp.callback_query(F.data == "add_item")
async def cb_add_item(callback: CallbackQuery):
    user_states[callback.from_user.id] = {'action': 'awaiting_list_item', 'thread_id': callback.message.message_thread_id}
    await callback.message.edit_text("Гав! Напиши, что добавить в список:")
    await callback.answer()

@dp.callback_query(F.data == "show_list")
async def cb_show_list(callback: CallbackQuery):
    thread_id = callback.message.message_thread_id
    async with aiosqlite.connect(DB_PATH) as db:
        if thread_id:
            query = "SELECT id, item_text FROM checklists WHERE chat_id = ? AND thread_id = ? AND is_done = 0 ORDER BY id ASC"
            params = (callback.message.chat.id, thread_id)
        else:
            query = "SELECT id, item_text FROM checklists WHERE chat_id = ? AND thread_id IS NULL AND is_done = 0 ORDER BY id ASC"
            params = (callback.message.chat.id,)

        async with db.execute(query, params) as cursor:
            items = await cursor.fetchall()

    if not items:
        await callback.message.edit_text("📭 Список пуст.", reply_markup=get_list_kb(thread_id))
        await callback.answer()
        return

    response = "📝 **Текущий список:**\n\n"
    keyboard = []
    for item in items:
        response += f"• {item[1]}\n"
        keyboard.append([InlineKeyboardButton(text=f"✅ {item[1]}", callback_data=f"done_{item[0]}")])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_lists")])
    await callback.message.edit_text(response, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data.startswith("done_"))
async def cb_mark_done(callback: CallbackQuery):
    item_id = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE checklists SET is_done = 1 WHERE id = ?", (item_id,))
        await db.commit()
    await callback.answer("✅ Вычеркнуто!")
    await cb_show_list(callback)

@dp.callback_query(F.data == "clear_list")
async def cb_clear_list(callback: CallbackQuery):
    thread_id = callback.message.message_thread_id
    async with aiosqlite.connect(DB_PATH) as db:
        if thread_id:
            await db.execute("DELETE FROM checklists WHERE chat_id = ? AND thread_id = ?", (callback.message.chat.id, thread_id))
        else:
            await db.execute("DELETE FROM checklists WHERE chat_id = ? AND thread_id IS NULL", (callback.message.chat.id,))
        await db.commit()
    await callback.message.edit_text("🗑️ Список очищен.", reply_markup=get_list_kb(thread_id))
    await callback.answer()

# --- РАНДОМАЙЗЕР ---
@dp.callback_query(F.data == "random_chore")
async def cb_random_chore(callback: CallbackQuery):
    names = list(user_tags.values())
    if len(names) < 2:
        names = ["Красавчик", "Бибизянка"]
    
    loser = random.choice(names)
    await callback.message.edit_text(
        f"🎲 Барабанная дробь...\n\nСегодня это делает: **{loser}**! 🧹🍽",
        parse_mode="Markdown",
        reply_markup=get_main_kb(callback.message.message_thread_id)
    )
    await callback.answer()

# --- КОМПЛИМЕНТ ---
@dp.callback_query(F.data == "compliment")
async def cb_compliment(callback: CallbackQuery):
    compliments = [
        "Ты мой самый любимый человек на свете! ❤️",
        "С тобой даже мыть посуду веселее. 😄",
        "Ты выглядишь потрясающе сегодня! 😍",
        "Спасибо, что ты есть. Ты делаешь этот мир лучше. ✨",
        "Ты самый умный и заботливый(ая) на свете! 🧠"
    ]
    text = random.choice(compliments)
    await callback.message.edit_text(
        f"💌 **Послание любви:**\n\n_{text}_",
        parse_mode="Markdown",
        reply_markup=get_main_kb(callback.message.message_thread_id)
    )
    await callback.answer()

# --- НАПОМИНАНИЯ ---
@dp.callback_query(F.data == "add_reminder")
async def cb_add_reminder(callback: CallbackQuery):
    user_states[callback.from_user.id] = {'action': 'awaiting_reminder', 'thread_id': callback.message.message_thread_id}
    await callback.message.edit_text("⏰ Напиши время и текст в формате:\n`ЧЧ:ММ Текст`\n\nПример: `18:30 Позвонить маме`", parse_mode="Markdown")
    await callback.answer()

# --- ОБРАБОТКА ТЕКСТА ---
@dp.message(F.text)
async def handle_text(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state:
        return

    action = state.get('action')
    thread_id = state.get('thread_id')
    user_states.pop(message.from_user.id, None)

    if action == 'awaiting_list_item':
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO checklists (chat_id, thread_id, item_text, added_by) VALUES (?, ?, ?, ?)",
                (message.chat.id, thread_id, message.text, user_tags.get(message.from_user.id) or message.from_user.first_name or "друг")
            )
            await db.commit()
        await message.reply(f"✅ Добавил: _{message.text}_", reply_markup=get_main_kb(thread_id))
        return

    if action == 'awaiting_reminder':
        try:
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                raise ValueError("Нужно время и текст")
                
            time_str, reminder_text = parts[0], parts[1]
            now = datetime.now()
            
            target_time = datetime.strptime(time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            
            if target_time < now:
                target_time += timedelta(days=1)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO reminders (chat_id, thread_id, user_id, text, remind_time) VALUES (?, ?, ?, ?, ?)",
                    (message.chat.id, thread_id, message.from_user.id, reminder_text, target_time)
                )
                await db.commit()
            
            await message.reply(f"⏰ Гав! Напомню в {target_time.strftime('%H:%M')}:\n_{reminder_text}_", reply_markup=get_main_kb(thread_id))
        except Exception:
            await message.reply("⚠️ Не понял формат. Напиши: `18:30 Позвонить маме`", reply_markup=get_main_kb(thread_id))

# --- ФОНОВАЯ ПРОВЕРКА НАПОМИНАНИЙ ---
async def check_reminders():
    while True:
        try:
            now = datetime.now()
            time_threshold = now - timedelta(minutes=1)
            
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT id, chat_id, thread_id, text FROM reminders WHERE remind_time <= ? AND remind_time >= ?",
                    (now, time_threshold)
                ) as cursor:
                    due_reminders = await cursor.fetchall()
                
                for r in due_reminders:
                    r_id, chat_id, thread_id, text = r
                    try:
                        await bot.send_message(chat_id, f"🔔 **НАПОМИНАНИЕ:**\n_{text}_", message_thread_id=thread_id, parse_mode="Markdown")
                        await db.execute("DELETE FROM reminders WHERE id = ?", (r_id,))
                    except Exception as e:
                        print(f"Ошибка отправки напоминания: {e}")
                        
                await db.commit()
        except Exception as e:
            print(f"Ошибка в фоновом цикле напоминаний: {e}")
            
        await asyncio.sleep(30)

async def main():
    await init_db()
    asyncio.create_task(check_reminders())
    print(f"Бот запущен! Ждем кодовое слово: '{WAKE_WORD}'")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
