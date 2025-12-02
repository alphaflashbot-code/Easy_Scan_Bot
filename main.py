import telebot
import os
import speech_recognition as sr
from pydub import AudioSegment
from flask import Flask
from threading import Thread

# --- ЧАСТЬ 1: НАСТРОЙКИ ---
# Получаем токен из настроек Render (или вставьте его сюда вручную для тестов)
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Перешли мне голосовое сообщение, и я превращу его в текст. 🎙️ -> 📝")

# --- ЧАСТЬ 2: ЛОГИКА ГОЛОСОВЫХ ---
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        chat_id = message.chat.id
        bot.send_message(chat_id, "🎧 Слушаю и обрабатываю...")

        # 1. Скачиваем файл
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        ogg_filename = f"voice_{chat_id}.ogg"
        wav_filename = f"voice_{chat_id}.wav"

        # Сохраняем OGG
        with open(ogg_filename, 'wb') as new_file:
            new_file.write(downloaded_file)

        # 2. Конвертируем OGG -> WAV (Требует FFmpeg!)
        sound = AudioSegment.from_ogg(ogg_filename)
        sound.export(wav_filename, format="wav")

        # 3. Распознаем речь (через Google)
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_filename) as source:
            audio_data = recognizer.record(source)
            # language='ru-RU' — распознаем русский язык
            text = recognizer.recognize_google(audio_data, language='ru-RU')

        # 4. Отправляем результат
        bot.reply_to(message, f"🗣 Текст:\n{text}")

    except sr.UnknownValueError:
        bot.reply_to(message, "🤔 Не смог разобрать слова. Попробуй говорить четче.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
    finally:
        # 5. Уборка мусора
        if os.path.exists(ogg_filename): os.remove(ogg_filename)
        if os.path.exists(wav_filename): os.remove(wav_filename)

# --- ЧАСТЬ 3: СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is listening..."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
