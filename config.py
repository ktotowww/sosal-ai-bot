import os
import logging

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") 
DATABASE_URL = os.environ.get("DATABASE_URL") 
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 10000))

DEFAULT_TEXT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_GEMMA_MODEL = "gemma-4-31b-it"
COOLDOWN_TIME = 0        
MAX_DAILY_REQUESTS = 50   

LEGACY_PEOPLE_MARKER = "БАЗА ДАННЫХ О ЛЮДЯХ"


def _prepare_prompt(raw_prompt):
    # В старых промптах переносы строк могли сохраниться как литеральные "\n".
    prompt = raw_prompt.replace("\\n", "\n").strip()

    # Если на Render ещё лежит старый промпт с людьми — вырезаем этот блок,
    # чтобы он не раздувал контекст. Данные о людях теперь живут в people.json.
    marker_pos = prompt.find(LEGACY_PEOPLE_MARKER)
    if marker_pos != -1:
        base_prompt_pos = prompt.find("Ты Sosal AI", marker_pos + len(LEGACY_PEOPLE_MARKER))
        if base_prompt_pos != -1:
            logger.warning("Из системного промпта вырезан устаревший блок о людях.")
            prompt = (prompt[:marker_pos] + prompt[base_prompt_pos:]).strip()

    return prompt


def load_system_prompt():
    render_secret_path = "/etc/secrets/system_prompt.txt"
    local_prompt_path = "system_prompt.txt"

    if os.path.exists(render_secret_path):
        try:
            with open(render_secret_path, "r", encoding="utf-8") as f:
                logger.info("Системный промпт успешно загружен из Render Secret Files.")
                return _prepare_prompt(f.read())
        except Exception as e:
            logger.error(f"Ошибка чтения промпта из {render_secret_path}: {e}")

    if os.path.exists(local_prompt_path):
        try:
            with open(local_prompt_path, "r", encoding="utf-8") as f:
                logger.info("Системный промпт успешно загружен из локального файла.")
                return _prepare_prompt(f.read())
        except Exception as e:
            logger.error(f"Ошибка чтения локального промпта: {e}")

    logger.warning("Файл промпта не найден. Используется базовый промпт по умолчанию.")
    return "Ты Sosal AI — ассистент с упором на Rust."

SYSTEM_PROMPT = load_system_prompt()
