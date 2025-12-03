import telebot
import os
from openai import OpenAI
from pydub import AudioSegment
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
# Берем токен Телеграма
TOKEN = os.environ.get('TOKEN')
# Берем ключ Groq (добавим его позже в настройки Render)
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

bot = telebot.TeleBot(TOKEN)

# Настраиваем клиент на сервера Groq
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Пришли ГС, я переведу его в текст с пунктуацией (Бесплатно через Whisper v3).")

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        chat_id = message.chat.id
        # Сообщаем пользователю, что процесс пошел
        msg = bot.send_message(chat_id, "🎧 Слушаю...")

        # 1. Скачиваем файл (он в формате .ogg)
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        ogg_filename = f"voice_{chat_id}.ogg"
        mp3_filename = f"voice_{chat_id}.mp3"

        with open(ogg_filename, 'wb') as new_file:
            new_file.write(downloaded_file)

        # 2. Конвертируем OGG -> MP3
        # (Groq лучше принимает MP3 или WAV)
        audio = AudioSegment.from_ogg(ogg_filename)
        audio.export(mp3_filename, format="mp3")

        # 3. Отправляем в Groq (Whisper Large v3)
        bot.edit_message_text("⚡️ Обрабатываю нейросетью...", chat_id, msg.message_id)
        
        with open(mp3_filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3", # Самая мощная модель
                file=audio_file,
                response_format="text"
            )

        # 4. Отправляем результат
        bot.send_message(chat_id, f"📝 Текст:\n\n{transcription}")
        # Удаляем сообщение "Обрабатываю..."
        bot.delete_message(chat_id, msg.message_id)

        # Уборка файлов
        os.remove(ogg_filename)
        os.remove(mp3_filename)

    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        # На всякий случай чистим файлы при ошибке
        if os.path.exists(ogg_filename): os.remove(ogg_filename)
        if os.path.exists(mp3_filename): os.remove(mp3_filename)

# --- СЕРВЕР ЧТОБЫ НЕ СПАЛ ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running on Groq power!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
