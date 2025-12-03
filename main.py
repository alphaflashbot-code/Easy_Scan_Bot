import telebot
import os
from openai import OpenAI
from pydub import AudioSegment
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# Вставь сюда свой канал, когда создашь (или оставь пустым пока)
CHANNEL_USERNAME = "@твоем_канале_тут" 

bot = telebot.TeleBot(TOKEN)
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# --- ПРИВЕТСТВИЕ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    keyboard = telebot.types.InlineKeyboardMarkup()
    # Если канал указан, добавляем кнопку
    if CHANNEL_USERNAME != "@твоем_канале_тут":
        url_button = telebot.types.InlineKeyboardButton(text="📢 Новости проекта", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        keyboard.add(url_button)
    
    bot.reply_to(message, 
                 "👋 **Привет!**\n\nЯ — умный секретарь. Перешли мне голосовое, и я:\n"
                 "1. 📝 Превращу его в текст.\n"
                 "2. 🧠 **Выделю главную суть** (Саммари).\n\n"
                 "Просто перешли мне сообщение!", 
                 parse_mode='Markdown', reply_markup=keyboard)

# --- ОБРАБОТКА ГОЛОСА ---
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        chat_id = message.chat.id
        msg = bot.send_message(chat_id, "🎧 **Слушаю и анализирую...**", parse_mode='Markdown')

        # 1. Скачиваем
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        ogg_filename = f"voice_{chat_id}.ogg"
        mp3_filename = f"voice_{chat_id}.mp3"

        with open(ogg_filename, 'wb') as new_file:
            new_file.write(downloaded_file)

        # 2. Конвертация
        audio = AudioSegment.from_ogg(ogg_filename)
        audio.export(mp3_filename, format="mp3")

        # 3. ШАГ 1: ТРАНСКРИБАЦИЯ (Whisper)
        bot.edit_message_text("✍️ **Записываю текст...**", chat_id, msg.message_id, parse_mode='Markdown')
        
        with open(mp3_filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text"
            )

        # 4. ШАГ 2: САММАРИЗАЦИЯ (Llama 3.3)
        summary_text = ""
        # Делаем саммари, только если текст длиннее 50 символов
        if len(transcription) > 50:
            bot.edit_message_text("🧠 **Выделяю главное...**", chat_id, msg.message_id, parse_mode='Markdown')
            
            completion = client.chat.completions.create(
                # ВОТ ЗДЕСЬ БЫЛА ОШИБКА, СТАВИМ НОВУЮ МОДЕЛЬ:
                model="llama-3.3-70b-versatile", 
                messages=[
                    {"role": "system", "content": "Ты профессиональный редактор. Твоя задача: прочитать текст голосового сообщения и написать краткую выжимку (Summary) на русском языке. Выдели главные мысли пунктами. Не пиши вступлений типа 'вот пересказ', сразу суть."},
                    {"role": "user", "content": f"Текст сообщения: {transcription}"}
                ],
                temperature=0.5,
            )
            summary_text = completion.choices[0].message.content

        # 5. ФОРМИРУЕМ ОТВЕТ
        final_response = f"📝 **Полный текст:**\n{transcription}\n\n"
        
        if summary_text:
            final_response += f"🧠 **Кратко (Суть):**\n{summary_text}\n"

        final_response += f"\n🤖 _Сделано в @{bot.get_me().username}_"

        bot.send_message(chat_id, final_response, parse_mode='Markdown')
        bot.delete_message(chat_id, msg.message_id)

        # Уборка
        os.remove(ogg_filename)
        os.remove(mp3_filename)

    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        # Чистим мусор даже при ошибке
        if os.path.exists(ogg_filename): os.remove(ogg_filename)
        if os.path.exists(mp3_filename): os.remove(mp3_filename)

# --- СЕРВЕР ---
app = Flask('')

@app.route('/')
def home():
    return "AI Bot Updated"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
