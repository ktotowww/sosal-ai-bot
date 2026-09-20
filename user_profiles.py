import logging
from config import DATABASE_URL
from database import get_db_ctx

logger = logging.getLogger(__name__)

MAX_PROFILE_LENGTH = 500


def init_profiles_table():
    if not DATABASE_URL:
        return
    with get_db_ctx() as conn:
        if not conn:
            return
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id    BIGINT PRIMARY KEY,
                            username   VARCHAR(100),
                            profile    TEXT DEFAULT '',
                            updated_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
        except Exception as e:
            logger.error(f"Ошибка создания user_profiles: {e}")


def save_user_profile(user_id, username, profile):
    if not DATABASE_URL:
        return
    with get_db_ctx() as conn:
        if not conn:
            return
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_profiles (user_id, username, profile, updated_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (user_id) DO UPDATE
                        SET profile = EXCLUDED.profile,
                            username = EXCLUDED.username,
                            updated_at = NOW();
                    """, (user_id, username, profile[:MAX_PROFILE_LENGTH]))
        except Exception as e:
            logger.error(f"Ошибка сохранения профиля {username}: {e}")


def get_user_profile(user_id):
    if not DATABASE_URL:
        return None
    with get_db_ctx() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT profile FROM user_profiles WHERE user_id = %s;", (user_id,))
                res = cur.fetchone()
                if res and res[0]:
                    return res[0]
        except Exception as e:
            logger.error(f"Ошибка чтения профиля {user_id}: {e}")
    return None


def get_profile_by_username(username):
    if not DATABASE_URL:
        return None
    clean = username.lstrip("@").lower()
    with get_db_ctx() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT profile FROM user_profiles WHERE LOWER(username) = %s OR LOWER(username) = %s;",
                    (clean, f"@{clean}")
                )
                res = cur.fetchone()
                if res and res[0]:
                    return res[0]
        except Exception as e:
            logger.error(f"Ошибка чтения профиля @{clean}: {e}")
    return None


def get_all_profiles():
    if not DATABASE_URL:
        return []
    with get_db_ctx() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, profile FROM user_profiles WHERE profile IS NOT NULL AND profile != '' ORDER BY updated_at DESC;"
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Ошибка загрузки профилей: {e}")
    return []


def build_profiles_section():
    profiles = get_all_profiles()
    if not profiles:
        return ""
    lines = []
    for i, (username, profile) in enumerate(profiles, 1):
        uname = f"@{username}" if not username.startswith("@") else username
        lines.append(f"{i}. {uname} — {profile}")
    section = "\nДИНАМИЧЕСКИЕ ПРОФИЛИ ПОЛЬЗОВАТЕЛЕЙ (собраны из переписки):\n" + "\n".join(lines)
    return section
