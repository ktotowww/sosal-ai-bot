import re
import threading
import logging
import requests
from config import GOOGLE_API_KEY, SYSTEM_PROMPT, DEFAULT_TEXT_MODEL, FALLBACK_GEMMA_MODEL
from database import get_user_config, get_user_context, save_user_context

logger = logging.getLogger(__name__)

EXTRACT_PROFILE_PROMPT = (
    "Тебе дан профиль пользователя и его новое сообщение. "
    "Обнови профиль: кратко опиши кто этот человек, чем занимается, его интересы и навыки. "
    "Максимум 2-3 предложения, без имён и обращений, только факты из сообщения. "
    "Если сообщение не содержит полезной информации о человеке (просто болтовня, мемы, стикеры) — верни текущий профиль без изменений.\n\n"
    "Текущий профиль: {profile}\n\n"
    "Новое сообщение: {message}"
)


def _build_system_prompt_with_profiles():
    profiles_section = __import__('user_profiles', fromlist=['build_profiles_section']).build_profiles_section()
    if profiles_section:
        return SYSTEM_PROMPT + "\n\n" + profiles_section
    return SYSTEM_PROMPT


def _extract_profile_background(user_id, username, user_text):
    try:
        from user_profiles import get_user_profile, save_user_profile

        existing = get_user_profile(user_id) or ""
        extraction_prompt = EXTRACT_PROFILE_PROMPT.format(profile=existing or "нет профиля", message=user_text)

        model = FALLBACK_GEMMA_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GOOGLE_API_KEY}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": extraction_prompt}]}],
            "systemInstruction": {"parts": [{"text": "Ты — система извлечения данных о пользователях. Отвечай ТОЛЬКО обновлённым профилем, без пояснений."}]},
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            result = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            result = re.sub(r'<thought>.*?</thought>', '', result, flags=re.DOTALL).strip()
            if result and len(result) > 10:
                save_user_profile(user_id, username, result)
                logger.info(f"Профиль @{username} обновлён: {result[:80]}...")
    except Exception as e:
        logger.error(f"Ошибка извлечения профиля @{username}: {e}")

def request_google_studio(model_slug, history, current_text, media_base64=None, mime_type="image/jpeg", system_prompt_override=None):
    if not GOOGLE_API_KEY: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_slug}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}

    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["text"]}]})

    current_parts = [{"text": current_text}]
    if media_base64:
        current_parts.append({"inlineData": {"mimeType": mime_type, "data": media_base64}})

    contents.append({"role": "user", "parts": current_parts})

    prompt_to_use = system_prompt_override or SYSTEM_PROMPT
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": prompt_to_use}]},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    if "gemma" in model_slug.lower():
        payload["generationConfig"] = {
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_json = response.json()
            try:
                parts = res_json['candidates'][0]['content']['parts']
                text_parts = [part.get("text", "") for part in parts if not part.get("thought")]
                result = "".join(text_parts).strip()
                
                result = re.sub(r'<\|channel\|>thought.*?<\|channel\|>', '', result, flags=re.DOTALL)
                result = re.sub(r'<\|channel>thought.*?<channel\|>', '', result, flags=re.DOTALL)
                result = re.sub(r'<\|channel\|>.*?<\|channel\|>', '', result, flags=re.DOTALL)
                result = re.sub(r'<\|channel>.*?<channel\|>', '', result, flags=re.DOTALL)
                result = re.sub(r'<thought>.*?</thought>', '', result, flags=re.DOTALL)
                
                return result.strip() if result.strip() else None
            except (KeyError, IndexError):
                try:
                    return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                except Exception:
                    return None
        else:
            logger.error(f"Google API [{model_slug}] ошибка HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Ошибка Google API Studio ({model_slug}): {e}")
    return None

def ask_text_ai(username, text, real_user_id, media_base64=None, mime_type="image/jpeg", bypass_history=False):
    config = get_user_config(real_user_id)
    chosen_model = config["text_model"]
    
    if media_base64 and "gemma" in chosen_model:
        return "⚠️ Модуль мультимедиа доступен только на чипах серии GEMINI FLASH. Переключи движок вычислителя в /models."
        
    history = [] if bypass_history else get_user_context(real_user_id)
    formatted_user_text = text if bypass_history else f"[{username}]: {text}"

    full_prompt = _build_system_prompt_with_profiles()

    result = request_google_studio(chosen_model, history, formatted_user_text, media_base64, mime_type, system_prompt_override=full_prompt)

    if not result and chosen_model == DEFAULT_TEXT_MODEL:
        logger.warning(f"Gemini Flash не ответил. Перегруз на {FALLBACK_GEMMA_MODEL}...")
        result = request_google_studio(FALLBACK_GEMMA_MODEL, history, formatted_user_text, media_base64, mime_type, system_prompt_override=full_prompt)

    if not result and chosen_model != DEFAULT_TEXT_MODEL:
        result = request_google_studio(DEFAULT_TEXT_MODEL, history, formatted_user_text, media_base64, mime_type, system_prompt_override=full_prompt)

    if result and not bypass_history:
        if "🚨" not in result and "⚠️" not in result:
            history.append({"role": "user", "text": formatted_user_text})
            history.append({"role": "bot", "text": result})
            save_user_context(real_user_id, history)

        if not bypass_history and username and not username.startswith("Guest_") and not username.startswith("System"):
            threading.Thread(
                target=_extract_profile_background,
                args=(real_user_id, username.lstrip("@"), text),
                daemon=True
            ).start()

    return result if result else "🚨 Сегфолт всех процессоров Sosaltix2. Сишники задосили шлюзы."
