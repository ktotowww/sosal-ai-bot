import time
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
                    cur.execute("ALTER TABLE bot_users ADD COLUMN IF NOT EXISTS daily_requests INT DEFAULT 0;")
                    cur.execute("ALTER TABLE bot_users ADD COLUMN IF NOT EXISTS total_requests BIGINT DEFAULT 0;")
                    cur.execute("""
                        UPDATE bot_users
                        SET daily_requests = daily_count
                        WHERE daily_requests = 0
                          AND daily_count > 0
                          AND last_request_date = CURRENT_DATE;
                    """)

                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id    BIGINT PRIMARY KEY,
                            username   VARCHAR(100),
                            profile    TEXT DEFAULT '',
                            updated_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")

def check_and_increment_daily_limit(user_id):
    if not DATABASE_URL:
        return True, 99
    with get_db_ctx() as conn:
        if not conn:
            return True, 99
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT daily_count, is_premium, text_model,
                               (last_request_date = CURRENT_DATE) AS is_today
                        FROM bot_users WHERE user_id = %s;
                    """, (user_id,))
                    res = cur.fetchone()

                    if not res:
                        cur.execute("""
                            INSERT INTO bot_users
                                (user_id, last_request_date, daily_count, daily_requests, total_requests, is_premium)
                            VALUES (%s, CURRENT_DATE, 1, 1, 1, FALSE);
                        """, (user_id,))
                        return True, MAX_DAILY_REQUESTS - 1

                    daily_count, is_premium, text_model, is_today = res
                    daily_count = daily_count or 0

                    if not is_today:
                        daily_count = 0
                        cur.execute("""
                            UPDATE bot_users
                            SET last_request_date = CURRENT_DATE, daily_count = 0, daily_requests = 0
                            WHERE user_id = %s;
                        """, (user_id,))

                    # Статистику ведём для всех, включая premium и Gemma.
                    cur.execute("""
                        UPDATE bot_users
                        SET daily_requests = COALESCE(daily_requests, 0) + 1,
                            total_requests = COALESCE(total_requests, 0) + 1,
                            last_request_date = CURRENT_DATE
                        WHERE user_id = %s;
                    """, (user_id,))

                    if is_premium or (text_model and "gemma" in text_model.lower()):
                        return True, 9999

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


def get_admin_stats():
    if not DATABASE_URL:
        return None
    with get_db_ctx() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_users,
                        COUNT(*) FILTER (WHERE last_request_date = CURRENT_DATE AND daily_requests > 0) AS active_today,
                        COALESCE(SUM(daily_requests) FILTER (WHERE last_request_date = CURRENT_DATE), 0) AS requests_today,
                        COALESCE(SUM(total_requests), 0) AS total_requests,
                        COUNT(*) FILTER (WHERE is_premium) AS premium_users
                    FROM bot_users;
                """)
                row = cur.fetchone()

                cur.execute("""
                    SELECT COALESCE(text_model, 'unknown'), COUNT(*)
                    FROM bot_users
                    GROUP BY text_model
                    ORDER BY COUNT(*) DESC;
                """)
                models = cur.fetchall()

            return {
                "total_users": int(row[0]),
                "active_today": int(row[1]),
                "requests_today": int(row[2]),
                "total_requests": int(row[3]),
                "premium_users": int(row[4]),
                "models": models,
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
    return None


def get_all_user_ids():
    if not DATABASE_URL:
        return []
    with get_db_ctx() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM bot_users WHERE user_id > 0 ORDER BY user_id;")
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
    return []


def set_user_premium(user_id, enabled=None):
    if not DATABASE_URL:
        return None
    with get_db_ctx() as conn:
        if not conn:
            return None
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO bot_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                        (user_id,),
                    )
                    if enabled is None:
                        cur.execute(
                            "UPDATE bot_users SET is_premium = NOT is_premium WHERE user_id = %s RETURNING is_premium;",
                            (user_id,),
                        )
                    else:
                        cur.execute(
                            "UPDATE bot_users SET is_premium = %s WHERE user_id = %s RETURNING is_premium;",
                            (enabled, user_id),
                        )
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Ошибка установки premium для {user_id}: {e}")
    return None
