import time
import datetime
import json
import logging
import psycopg2
from contextlib import contextmanager
from config import DATABASE_URL, DEFAULT_TEXT_MODEL, FALLBACK_GEMMA_MODEL, MAX_DAILY_REQUESTS, COOLDOWN_TIME

logger = logging.getLogger(__name__)

user_cooldowns = {}

@contextmanager
def get_db_ctx():
    if not DATABASE_URL:
        yield None
        return
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        yield conn
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
        yield None
    finally:
        if conn:
            conn.close()

def init_db():
    if not DATABASE_URL:
        return
    with get_db_ctx() as conn:
        if not conn:
            return
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS bot_users (
                            user_id BIGINT PRIMARY KEY,
                            text_model VARCHAR(50) DEFAULT '{DEFAULT_TEXT_MODEL}',
                            image_model VARCHAR(50) DEFAULT 'flux',
                            last_request_date DATE DEFAULT CURRENT_DATE,
                            daily_count INT DEFAULT 0
                        );
                    """)
                    cur.execute("ALTER TABLE bot_users ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '[]'::jsonb;")
                    cur.execute("ALTER TABLE bot_users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE;")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")

def check_and_increment_daily_limit(user_id):
    current_date = datetime.date.today()
    if not DATABASE_URL:
        return True, 99
    with get_db_ctx() as conn:
        if not conn:
            return True, 99
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT last_request_date, daily_count, is_premium, text_model FROM bot_users WHERE user_id = %s;", (user_id,))
                    res = cur.fetchone()
                    
                    if not res:
                        cur.execute("INSERT INTO bot_users (user_id, last_request_date, daily_count, is_premium) VALUES (%s, %s, 1, FALSE);", (user_id, current_date))
                        return True, MAX_DAILY_REQUESTS - 1
                        
                    last_date, daily_count, is_premium, text_model = res
                    
                    if is_premium or (text_model and "gemma" in text_model.lower()):
                        return True, 9999
                        
                    if last_date != current_date:
                        cur.execute("UPDATE bot_users SET last_request_date = %s, daily_count = 1 WHERE user_id = %s;", (current_date, user_id))
                        return True, MAX_DAILY_REQUESTS - 1
                        
                    if daily_count >= MAX_DAILY_REQUESTS:
                        cur.execute("UPDATE bot_users SET text_model = %s WHERE user_id = %s;", (FALLBACK_GEMMA_MODEL, user_id))
                        return True, 9999
                        
                    new_count = daily_count + 1
                    cur.execute("UPDATE bot_users SET daily_count = %s WHERE user_id = %s;", (new_count, user_id))
                    return True, MAX_DAILY_REQUESTS - new_count
        except Exception as e:
            logger.error(f"Ошибка лимитов: {e}")
            return True, 99

def get_user_config(user_id):
    default_config = {"text_model": DEFAULT_TEXT_MODEL, "image_model": "flux"}
    if not DATABASE_URL: return default_config
    with get_db_ctx() as conn:
        if not conn: return default_config
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT text_model, image_model FROM bot_users WHERE user_id = %s;", (user_id,))
                    res = cur.fetchone()
                    if not res:
                        cur.execute("INSERT INTO bot_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (user_id,))
                        return default_config
                    else:
                        model_name = res[0]
                        if model_name in ['gemini', 'openai-large', 'qwen-large', 'gemma']:
                            model_name = DEFAULT_TEXT_MODEL
                        return {"text_model": model_name, "image_model": res[1]}
        except Exception as e:
            logger.error(f"Ошибка get_user_config: {e}")
            return default_config

def update_user_config(user_id, text_model=None, image_model=None):
    if not DATABASE_URL: return
    with get_db_ctx() as conn:
        if not conn: return
        try:
            with conn:
                with conn.cursor() as cur:
                    if text_model:
                        cur.execute("UPDATE bot_users SET text_model = %s WHERE user_id = %s;", (text_model, user_id))
                    if image_model:
                        cur.execute("UPDATE bot_users SET image_model = %s WHERE user_id = %s;", (image_model, user_id))
        except Exception as e:
            logger.error(f"Ошибка update_user_config: {e}")

def get_user_context(user_id):
    if not DATABASE_URL: return []
    with get_db_ctx() as conn:
        if not conn: return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT context FROM bot_users WHERE user_id = %s;", (user_id,))
                res = cur.fetchone()
                if res and res[0]: return res[0]
        except Exception as e:
            logger.error(f"Ошибка чтения контекста: {e}")
    return []

def save_user_context(user_id, context):
    if not DATABASE_URL: return
    with get_db_ctx() as conn:
        if not conn: return
        try:
            with conn:
                with conn.cursor() as cur:
                    trimmed_context = context[-10:]
                    cur.execute("UPDATE bot_users SET context = %s::jsonb WHERE user_id = %s;", (json.dumps(trimmed_context), user_id))
        except Exception as e:
            logger.error(f"Ошибка записи контекста: {e}")

def is_flooding(user_id):
    current_time = time.time()
    last_time = user_cooldowns.get(user_id, 0)
    if current_time - last_time < COOLDOWN_TIME:
        return True  
    user_cooldowns[user_id] = current_time
    return False
