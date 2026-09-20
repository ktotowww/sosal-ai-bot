import os
import time
import io
import base64
import threading
import logging
from PIL import Image
import telebot
from telebot import apihelper

from config import TELEGRAM_TOKEN
from database import init_db, is_flooding, check_and_increment_daily_limit
from handlers import register_handlers, send_answer_guest_query
from server import run_dummy_server
from ai_engine import ask_text_ai
from git_analyzer import fetch_github_repo, process_repo_zip
from github_comparator import compare_github_targets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

if not TELEGRAM_TOKEN:
    raise ValueError("ОШИБКА: TELEGRAM_TOKEN не найден в переменных окружения!")

apihelper.ENABLE_MIDDLEWARE = True

bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.middleware_handler(update_types=['guest_message'])
def handle_raw_guest_update(bot_instance, message_or_update):
    try:
        msg = getattr(message_or_update, 'guest_message', message_or_update)

        guest_query_id = getattr(msg, 'guest_query_id', None)
        user_text = getattr(msg, 'text', '') or getattr(msg, 'caption', '') or ''
        from_user = getattr(msg, 'from_user', None)

        user_id = from_user.id if from_user else 0
        username = f"@{from_user.username}" if (from_user and getattr(from_user, 'username', None)) else f"Guest_{user_id}"

        if not guest_query_id:
            return

        if is_flooding(user_id):
            send_answer_guest_query(bot_instance, guest_query_id, "⚠️ ЗАТКНИСЬ! Кулдаун — 8 секунд!")
            return

        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed:
            send_answer_guest_query(bot_instance, guest_query_id, "❌ ЛИМИТ ИСЧЕРПАН! Приходи завтра.")
            return

        photo = getattr(msg, 'photo', None)
        if photo:
            photo_item = photo[-1] if isinstance(photo, list) else photo
            file_info = bot_instance.get_file(photo_item.file_id)
            downloaded_file = bot_instance.download_file(file_info.file_path)
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')
            prompt_text = user_text if user_text else "Что на фото?"
            reply = ask_text_ai(username, prompt_text, user_id, media_base64=image_base64)
            send_answer_guest_query(bot_instance, guest_query_id, reply)
            return

        sticker = getattr(msg, 'sticker', None)
        if sticker:
            if getattr(sticker, 'is_animated', False):
                emoji = getattr(sticker, 'emoji', "🤔") or "🤔"
                send_answer_guest_query(bot_instance, guest_query_id, f"⚠️ Это векторный стикер (.tgs). Я вижу только его эмодзи: {emoji}")
                return

            file_info = bot_instance.get_file(sticker.file_id)
            downloaded_file = bot_instance.download_file(file_info.file_path)
            image = Image.open(io.BytesIO(downloaded_file)).convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

            sticker_emoji = getattr(sticker, 'emoji', "") or ""
            prompt_text = user_text or f"Опиши и оцени этот стикер (прикрепленный эмодзи: '{sticker_emoji}'). Прокомментируй его в своём стиле."
            reply = ask_text_ai(username, prompt_text, user_id, media_base64=image_base64, mime_type="image/jpeg")
            send_answer_guest_query(bot_instance, guest_query_id, reply)
            return

        video = getattr(msg, 'video', None) or getattr(msg, 'animation', None)
        if video:
            file_info = bot_instance.get_file(video.file_id)
            downloaded_file = bot_instance.download_file(file_info.file_path)
            mime_type = getattr(video, 'mime_type', None) or "video/mp4"
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')
            prompt_text = user_text if user_text else "Что происходит на этом видео?"
            reply = ask_text_ai(username, prompt_text, user_id, media_base64=image_base64, mime_type=mime_type)
            send_answer_guest_query(bot_instance, guest_query_id, reply)
            return

        voice = getattr(msg, 'voice', None)
        if voice:
            file_info = bot_instance.get_file(voice.file_id)
            downloaded_file = bot_instance.download_file(file_info.file_path)
            mime_type = getattr(voice, 'mime_type', None) or "audio/ogg"
            audio_base64 = base64.b64encode(downloaded_file).decode('utf-8')
            prompt_text = "Распознай и расшифруй речь из голосового сообщения и ответь по сути сказанного."
            reply = ask_text_ai(username, prompt_text, user_id, media_base64=audio_base64, mime_type=mime_type)
            send_answer_guest_query(bot_instance, guest_query_id, reply)
            return

        if user_text.startswith("/gitv") or ("github.com/" in user_text.lower() and "сравни" not in user_text.lower()):
            repo_url = None
            user_comment = "Проанализируй этот репозиторий."
            if user_text.startswith("/gitv"):
                parts = user_text.split(maxsplit=2)
                if len(parts) > 1:
                    repo_url = parts[1]
                    if len(parts) > 2:
                        user_comment = parts[2]
            else:
                for word in user_text.split():
                    if "github.com/" in word.lower():
                        repo_url = word
                        break

            if repo_url:
                zip_file, error_msg = fetch_github_repo(repo_url)
                if error_msg:
                    send_answer_guest_query(bot_instance, guest_query_id, error_msg)
                    return
                
                tree_str, code_str = process_repo_zip(zip_file)
                full_ai_prompt = (
                    f"Репозиторий GitHub: {repo_url}\nЗАПРОС: {user_comment}\n\n"
                    f"СТРУКТУРА:\n```\n{tree_str}\n```\n\nСОДЕРЖИМОЕ:\n{code_str}"
                )
                reply = ask_text_ai(username, full_ai_prompt, user_id)
                send_answer_guest_query(bot_instance, guest_query_id, reply)
                return

        if "сравни" in user_text.lower():
            compare_res = compare_github_targets(user_text, username, user_id)
            if compare_res:
                send_answer_guest_query(bot_instance, guest_query_id, compare_res)
                return

        if user_text:
            reply = ask_text_ai(username, user_text, user_id)
            send_answer_guest_query(bot_instance, guest_query_id, reply)

    except Exception as e:
        logger.error(f"Ошибка обработки guest_message: {e}")

def start_polling():
    while True:
        try:
            bot.remove_webhook()
            logger.info("Ядро Sosal AI запущено...")
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True,
                allowed_updates=["message", "edited_message", "callback_query", "guest_message"]
            )
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 409:
                logger.warning("Конфликт экземпляров (409). Ждём 5 секунд...")
                time.sleep(5)
            else:
                logger.error(f"Ошибка Telegram API ({e.error_code}): {e}. Перезапуск...")
                time.sleep(5)
        except Exception as e:
            logger.error(f"Сбой поллинга: {e}. Перезапуск...")
            time.sleep(5)

if __name__ == "__main__":
    init_db()
    register_handlers(bot)
    threading.Thread(target=run_dummy_server, daemon=True).start()
    start_polling()
