import os
import logging

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") 
DATABASE_URL = os.environ.get("DATABASE_URL") 
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 10000))

DEFAULT_TEXT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_GEMMA_MODEL = "gemma-4-31b-it"
COOLDOWN_TIME = 0        
MAX_DAILY_REQUESTS = 50   

def load_system_prompt():
    render_secret_path = "/etc/secrets/system_prompt.txt"
    local_prompt_path = "system_prompt.txt"

    if os.path.exists(render_secret_path):
        try:
            with open(render_secret_path, "r", encoding="utf-8") as f:
                logger.info("Системный промпт успешно загружен из Render Secret Files.")
                return f.read().strip()
        except Exception as e:
            logger.error(f"Ошибка чтения промпта из {render_secret_path}: {e}")

    if os.path.exists(local_prompt_path):
        try:
            with open(local_prompt_path, "r", encoding="utf-8") as f:
                logger.info("Системный промпт успешно загружен из локального файла.")
                return f.read().strip()
        except Exception as e:
            logger.error(f"Ошибка чтения локального промпта: {e}")

    logger.warning("Файл промпта не найден. Используется базовый промпт по умолчанию.")
    return "Ты Sosal AI — ассистент с упором на Rust."

SYSTEM_PROMPT = load_system_prompt()
