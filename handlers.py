import io
from PIL import Image
import time
import base64
import urllib.parse
import psycopg2
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID, DATABASE_URL, TELEGRAM_TOKEN
from database import (
    is_flooding, check_and_increment_daily_limit, get_user_config,
    update_user_config, save_user_context
)
from ai_engine import ask_text_ai
from git_analyzer import fetch_github_repo, process_repo_zip
from github_comparator import compare_github_targets

BOT_USERNAME = None
BOT_ID = None

BOT_CALLS = ["сосал ии", "sosal ai"]

from telebot.types import InlineQueryResultArticle, InputTextMessageContent

def send_answer_guest_query(bot_instance, guest_query_id, text, title="Sosal AI Response"):
    try:
        result = InlineQueryResultArticle(
            id="guest_1",
            title=title,
            input_message_content=InputTextMessageContent(
                message_text=text,
                parse_mode="Markdown"
            )
        )
        bot_instance.answer_guest_query(guest_query_id, result)
    except Exception as e:
        print(f"[-] Ошибка send_answer_guest_query: {e}")

def register_handlers(bot):
    global BOT_USERNAME, BOT_ID
    try:
        bot_info = bot.get_me()
        BOT_USERNAME = bot_info.username
        BOT_ID = bot_info.id
        print(f"[+] Авторизован как @{BOT_USERNAME}")
    except Exception as e:
        print(f"[-] Ошибка получения профиля бота: {e}")

    def should_respond(message):
        if message.chat.type == 'private':
            return True

        text_to_check = message.text or message.caption or ""
        text_lower = text_to_check.lower()

        if message.reply_to_message and message.reply_to_message.from_user:
            if BOT_ID and message.reply_to_message.from_user.id == BOT_ID:
                return True
            if BOT_USERNAME and message.reply_to_message.from_user.username == BOT_USERNAME:
                return True

        if BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text_lower:
            return True
        if any(call in text_lower for call in BOT_CALLS):
            return True

        triggers = ["c++", "си плюс плюс", "си++", "zinux", "зинкус", "ассемблер", "с", "pros", "sosaltix", "сосалтикс"]
        if any(t in text_lower for t in triggers):
            return True
        if " си " in f" {text_lower} ":
            return True

        return False

    def make_models_keyboard(user_id):
        config = get_user_config(user_id)
        markup = InlineKeyboardMarkup()

        t_gemini = "✅ Gemini Flash" if config["text_model"] == "gemini-3.1-flash-lite" else "Gemini Flash"
        t_gemma31 = "✅ Gemma 4 31B (Unlimited)" if config["text_model"] == "gemma-4-31b-it" else "Gemma 4 31B (Unlimited)"
        t_gemma26 = "✅ Gemma 4 26B (Unlimited)" if config["text_model"] == "gemma-4-26b-a4b-it" else "Gemma 4 26B (Unlimited)"

        i_flux = "✅ Flux (HQ)" if config["image_model"] == "flux" else "Flux (HQ)"
        i_zimage = "✅ ZImage (No Cens)" if config["image_model"] == "zimage" else "ZImage (No Cens)"

        markup.row(InlineKeyboardButton("📝 ТЕКСТОВЫЕ ДВИЖКИ GOOGLE STUDIO:", callback_data="void"))
        markup.row(InlineKeyboardButton(t_gemini, callback_data="ui_txt_gemini-3.1-flash-lite"))
        markup.row(InlineKeyboardButton(t_gemma31, callback_data="ui_txt_gemma-4-31b-it"), InlineKeyboardButton(t_gemma26, callback_data="ui_txt_gemma-4-26b-a4b-it"))

        markup.row(InlineKeyboardButton("🎨 ГРАФИЧЕСКИЕ ДВИЖКИ (POLLINATIONS):", callback_data="void"))
        markup.row(InlineKeyboardButton(i_flux, callback_data="ui_img_flux"), InlineKeyboardButton(i_zimage, callback_data="ui_img_zimage"))

        markup.row(InlineKeyboardButton("🗑 ОЧИСТИТЬ КОНТЕКСТ (ПАМЯТЬ)", callback_data="ui_clear_context"))
        return markup

    def build_menu_text(config):
        return f"⚙️ **Панель управления ядра Sosal AI**\n\n● Текстовый чип: `{config['text_model'].upper()}`\n● Графический чип: `{config['image_model'].upper()}`\n\nВыбирай вычислительные модули кнопками ниже:"

    @bot.callback_query_handler(func=lambda call: call.data.startswith("ui_"))
    def handle_menu_clicks(call):
        user_id = call.from_user.id
        action = call.data.replace("ui_", "")

        if action == "clear_context":
            save_user_context(user_id, [])
            bot.answer_callback_query(call.id, "🧠 Память очищена! Ядро Sosaltix2 сброшено.", show_alert=True)
            try:
                config = get_user_config(user_id)
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=build_menu_text(config), reply_markup=make_models_keyboard(user_id), parse_mode="Markdown")
            except Exception: pass
            return

        if action.startswith("txt_"):
            new_model = action.replace("txt_", "")
            update_user_config(user_id, text_model=new_model)
            bot.answer_callback_query(call.id, f"Текстовый чип: {new_model.upper()}")
        elif action.startswith("img_"):
            new_img = action.replace("img_", "")
            update_user_config(user_id, image_model=new_img)
            bot.answer_callback_query(call.id, f"Графика: {new_img.upper()}")

        try:
            updated_config = get_user_config(user_id)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=build_menu_text(updated_config), reply_markup=make_models_keyboard(user_id), parse_mode="Markdown")
        except Exception: pass

    @bot.message_handler(commands=['models', 'settings'])
    def show_models_menu(message):
        user_id = message.from_user.id
        config = get_user_config(user_id)
        bot.send_message(message.chat.id, build_menu_text(config), reply_markup=make_models_keyboard(user_id), parse_mode="Markdown")

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        username = f"@{message.from_user.username}" if message.from_user.username else "Чушпан"
        if "Nortonqq" in username:
            bot.reply_to(message, "О, кодер на Zinux пришел. Смени движок через /models, пока твоя память не утекла.")
        elif "voiduser777" in username:
            bot.reply_to(message, "@voiduser777 в чате, пакуем пакеты. Настройки твоего cgit тут -> /models.")
        elif "ktotowww" in username:
            bot.reply_to(message, "Приветствую, о Великий @ktotowww! Я готов компилировать код под Sosaltix2! Панель: /models.")
        else:
            bot.reply_to(message, "Че надо? Настройки моделей: /models, генерация картинок: /pic.")

    @bot.message_handler(commands=['pic', 'meme'])
    def generate_meme(message):
        user_id = message.from_user.id
        if is_flooding(user_id):
            bot.reply_to(message, "⚠️ ЗАТКНИСЬ! Кулдаун — 8 секунд!")
            return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed:
            bot.reply_to(message, "❌ ЛИМИТ ИСЧЕРПАН! Приходи завтра.")
            return

        user_prompt = message.text.split(maxsplit=1)
        if len(user_prompt) < 2:
            bot.reply_to(message, "Напиши промт: /pic сишник плачет над сегфолтом")
            return

        raw_prompt_text = user_prompt[1]
        config = get_user_config(user_id)
        chosen_img_model = config["image_model"]
        bot.reply_to(message, f"🎛 Компилятор задействует ядро {chosen_img_model.upper()}... Рендерю арт, жди.")

        system_prompter = "Translate from Russian to English and expand into detailed prompt. Output ONLY English."
        enhanced_prompt = ask_text_ai("System_Prompter", f"{system_prompter}\n\nUser request: {raw_prompt_text}", user_id, bypass_history=True)
        if "🚨" in enhanced_prompt or len(enhanced_prompt) > 1000: enhanced_prompt = raw_prompt_text

        try:
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            final_image_url = f"https://image.pollinations.ai/p/{encoded_prompt}?model={chosen_img_model}&width=1024&height=1024&nologo=true&enhance=true&private=true"
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.send_photo(message.chat.id, final_image_url, caption=f"🖼 Модуль: {chosen_img_model.upper()}")
        except Exception:
            bot.reply_to(message, "Графический чип упал в сегфолт.")

    @bot.message_handler(commands=['gitv'])
    def handle_gitv_command(message):
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"

        if is_flooding(user_id):
            bot.reply_to(message, "⚠️ ЗАТКНИСЬ! Кулдаун — 8 секунд!")
            return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed:
            bot.reply_to(message, "❌ ЛИМИТ ИСЧЕРПАН! Приходи завтра.")
            return

        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Использование: `/gitv <ссылка> [комментарий]`", parse_mode="Markdown")
            return

        repo_url = args[1]
        user_comment = args[2] if len(args) > 2 else "Проанализируй этот репозиторий."
        status_msg = bot.reply_to(message, "🔍 Клонирую репозиторий в память Sosaltix2...")

        zip_file, error_msg = fetch_github_repo(repo_url)
        if error_msg:
            bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=error_msg)
            return

        try:
            tree_str, code_str = process_repo_zip(zip_file)
            full_ai_prompt = (
                f"Репозиторий GitHub: {repo_url}\nЗАПРОС: {user_comment}\n\n"
                f"СТРУКТУРА:\n```\n{tree_str}\n```\n\nСОДЕРЖИМОЕ:\n{code_str}"
            )
            reply = ask_text_ai(username, full_ai_prompt, user_id)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
            bot.reply_to(message, reply)
        except Exception:
            bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text="🚨 Критическая ошибка разбора кода.")

    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        if message.from_user.id != ADMIN_ID:
            return
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            bot.reply_to(message, "🛠 `/admin stats` | `/admin broadcast <текст>` | `/admin premium <id> [on/off]`", parse_mode="Markdown")
            return

        subcommand = args[1].lower()
        if subcommand == "stats" and DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM bot_users;")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*), COALESCE(SUM(daily_count), 0) FROM bot_users WHERE last_request_date = CURRENT_DATE;")
            active_today, requests_today = cur.fetchone()
            cur.close()
            conn.close()
            bot.reply_to(message, f"👤 Пользователей: `{total_users}`\n🏃 Активных: `{active_today}`\n📈 Запросов: `{requests_today}`", parse_mode="Markdown")

    @bot.message_handler(content_types=['photo'])
    def handle_incoming_photo(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        user_text = message.caption if message.caption else "Что на фото?"
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')
            reply = ask_text_ai(username, user_text, user_id, media_base64=image_base64)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)
        except Exception:
            bot.reply_to(message, "🚨 Не удалось прочитать изображение.")

    @bot.message_handler(content_types=['sticker'])
    def handle_incoming_sticker(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        try:
            if message.sticker.is_animated:
                emoji = message.sticker.emoji or "🤔"
                bot.reply_to(message, f"⚠️ Это векторный стикер (.tgs). Я вижу только его эмодзи: {emoji}")
                return

            file_info = bot.get_file(message.sticker.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            image = Image.open(io.BytesIO(downloaded_file))
            image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            sticker_emoji = message.sticker.emoji or ""
            prompt_text = f"Опиши и оцени этот стикер (прикрепленный эмодзи: '{sticker_emoji}'). Прокомментируй его в своём стиле."

            reply = ask_text_ai(username, prompt_text, user_id, media_base64=image_base64, mime_type="image/jpeg")
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)

        except Exception as e:
            print(f"[-] Ошибка обработки стикера: {e}")
            bot.reply_to(message, "🚨 Не удалось распознать стикер.")

    @bot.message_handler(content_types=['animation'])
    def handle_incoming_animation(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        try:
            file_info = bot.get_file(message.animation.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            mime_type = message.animation.mime_type or "video/mp4"
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

            caption_text = message.caption if message.caption else "Что происходит на этой гифке?"

            reply = ask_text_ai(username, caption_text, user_id, media_base64=image_base64, mime_type=mime_type)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)

        except Exception as e:
            print(f"[-] Ошибка обработки анимации: {e}")
            bot.reply_to(message, "🚨 Не удалось разбрать гифку.")

    @bot.message_handler(content_types=['document'])
    def handle_incoming_document(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_content = downloaded_file.decode('utf-8', errors='ignore')[:15000]
            user_comment = message.caption if message.caption else "Проанализируй файл."
            full_ai_prompt = f"Файл '{message.document.file_name}':\n```\n{file_content}\n```\n{user_comment}"
            reply = ask_text_ai(username, full_ai_prompt, user_id)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)
        except Exception:
            bot.reply_to(message, "🚨 Сбой дешифрации файла.")

    @bot.message_handler(content_types=['video'])
    def handle_incoming_video(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        try:
            file_info = bot.get_file(message.video.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            mime_type = message.video.mime_type or "video/mp4"
            image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

            caption_text = message.caption if message.caption else "Что происходит на этом видео?"

            reply = ask_text_ai(username, caption_text, user_id, media_base64=image_base64, mime_type=mime_type)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)

        except Exception as e:
            print(f"[-] Ошибка обработки видео: {e}")
            bot.reply_to(message, "🚨 Не удалось разобрать видео.")

    @bot.message_handler(content_types=['voice'])
    def handle_incoming_voice(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        try:
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            mime_type = message.voice.mime_type or "audio/ogg"
            audio_base64 = base64.b64encode(downloaded_file).decode('utf-8')
            prompt_text = "Распознай и расшифруй речь из голосового сообщения и ответь по сути сказанного."
            reply = ask_text_ai(username, prompt_text, user_id, media_base64=audio_base64, mime_type=mime_type)
            left_str = "Безлимит" if left > 1000 else f"{left}/50"
            bot.reply_to(message, reply)
        except Exception as e:
            print(f"[-] Ошибка обработки голосового сообщения: {e}")
            bot.reply_to(message, "🚨 Не удалось распознать голосовое сообщение.")

    @bot.message_handler(func=lambda message: True)
    def echo_all(message):
        if not should_respond(message): return
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"Юзер_{message.chat.id}"
        if is_flooding(user_id): return
        allowed, left = check_and_increment_daily_limit(user_id)
        if not allowed: return

        if "сравни" in message.text.lower():
            compare_res = compare_github_targets(message.text, username, user_id)
            if compare_res:
                left_str = "Безлимит" if left > 1000 else f"{left}/50"
                bot.reply_to(message, compare_res)
                return
                        
        reply = ask_text_ai(username, message.text, user_id)
        left_str = "Безлимит" if left > 1000 else f"{left}/50"
        bot.reply_to(message, reply)
