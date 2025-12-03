import telebot
import os
import sqlite3
from datetime import datetime, date
from openai import OpenAI
from pydub import AudioSegment
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
# Если канал не создан, оставь как есть или впиши юзернейм
CHANNEL_USERNAME = "@твоем_канале_тут"

# ТВОЙ ID АДМИНА (теперь бот слушается только тебя)
ADMIN_ID = 6035511012

bot = telebot.TeleBot(TOKEN)
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    """Создает таблицу, если её нет"""
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                join_date TEXT,
                last_active TEXT
            )
        ''')
        conn.commit()

def track_user(user_id):
    """Записывает юзера или обновляет дату его активности"""
    today = str(date.today())
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            cursor.execute('INSERT INTO users (user_id, join_date, last_active) VALUES (?, ?, ?)', 
                           (user_id, today, today))
        else:
            cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (today, user_id))
        conn.commit()

# Запускаем БД при старте
init_db()

# --- СТАТИСТИКА (Только для тебя) ---
@bot.message_handler(commands=['stats'])
def admin_stats(message):
    # Проверяем, ты ли это пишешь
    if message.from_user.id != ADMIN_ID:
        return # Если не ты, бот просто промолчит

    today = str(date.today())
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        
        # 1. Всего пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # 2. Новых за сегодня
        cursor.execute('SELECT COUNT(*) FROM users WHERE join_date = ?', (today,))
        new_today = cursor.fetchone()[0]
        
        # 3. Активных за сегодня
        cursor.execute('SELECT COUNT(*) FROM users WHERE last_active = ?', (today,))
        active_today = cursor.fetchone()[0]

    stat_text = (
        f"📊 **Статистика твоего бота:**\n\n"
        f"👥 **Всего юзеров:** {total_users}\n"
        f"🔥 **Активных сегодня:** {active_today}\n"
        f"🆕 **Новичков сегодня:** {new_today}\n\n"
        f"_Сделай скриншот этого сообщения для рекламодателя!_"
    )
    bot.reply_to(message, stat_text)

# --- ПРИВЕТСТВИЕ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    track_user(message.chat.id) # Считаем пользователя
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    if CHANNEL_USERNAME != "@твоем_канале_тут":
        url_button = telebot.types.InlineKeyboardButton(text="📢 Новости проекта", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        keyboard.add(url_button)
    
    bot.reply_to(message, 
                 "👋 Привет! Я — умный секретарь (Groq + Llama 3).\n"
                 "Перешли мне голосовое сообщение, и я пришлю текст + краткую суть.", 
                 reply_markup=keyboard)

# --- ОБРАБОТКА ГОЛОСА ---
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    track_user(message.chat.id) # Считаем пользователя

    try:
        chat_id = message.chat.id
        # Убрали Markdown, чтобы не было ошибок
        msg = bot.send_message(chat_id, "🎧 Слушаю...")

        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        ogg_filename = f"voice_{chat_id}.ogg"
        mp3_filename = f"voice_{chat_id}.mp3"

        with open(ogg_filename, 'wb') as new_file:
            new_file.write(downloaded_file)

        audio = AudioSegment.from_ogg(ogg_filename)
        audio.export(mp3_filename, format="mp3")

        # Whisper (Транскрибация)
        bot.edit_message_text("✍️ Пишу текст...", chat_id, msg.message_id)
        with open(mp3_filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text"
            )

        # Llama (Саммари)
        summary_text = ""
        if len(transcription) > 50:
            bot.edit_message_text("🧠 Выделяю суть...", chat_id, msg.message_id)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Твоя задача: написать краткую выжимку (Summary) текста на русском языке. Используй тире для списков. Сразу к сути."},
                    {"role": "user", "content": f"Текст: {transcription}"}
                ],
                temperature=0.5,
            )
            summary_text = completion.choices[0].message.content

        # Ответ
        final_response = f"📝 ПОЛНЫЙ ТЕКСТ:\n{transcription}\n\n"
        if summary_text:
            final_response += f"🧠 КРАТКО:\n{summary_text}\n"
        final_response += f"\n🤖 Сделано в @{bot.get_me().username}"

        bot.send_message(chat_id, final_response)
        bot.delete_message(chat_id, msg.message_id)

        os.remove(ogg_filename)
        os.remove(mp3_filename)

    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}")
        if os.path.exists(ogg_filename): os.remove(ogg_filename)
        if os.path.exists(mp3_filename): os.remove(mp3_filename)

# --- СЕРВЕР ---
app = Flask('')

@app.route('/')
def home():
    return "Bot with Stats is Live"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
