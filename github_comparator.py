import os
import re
import requests
from ai_engine import ask_text_ai

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

def fetch_github_profile_stats(username: str):
    headers = {
        "User-Agent": "Sosaltix-Bot",
        "Accept": "application/vnd.github.v3+json"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    clean_user = username.strip("@/ ")
    
    user_resp = requests.get(f"https://api.github.com/users/{clean_user}", headers=headers, timeout=10)
    if user_resp.status_code != 200:
        return None, f"HTTP {user_resp.status_code}"
    
    u_data = user_resp.json()
    repos_resp = requests.get(f"https://api.github.com/users/{clean_user}/repos?per_page=100", headers=headers, timeout=10)
    repos_data = repos_resp.json() if repos_resp.status_code == 200 else []
    
    languages = {}
    if isinstance(repos_data, list):
        for repo in repos_data:
            if isinstance(repo, dict):
                lang = repo.get("language")
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1

    return {
        "username": clean_user,
        "bio": u_data.get("bio") or "Описание отсутствует",
        "public_repos": u_data.get("public_repos", 0),
        "followers": u_data.get("followers", 0),
        "languages": languages
    }, None

def compare_github_targets(text: str, telegram_username: str, user_id: int):
    found_urls = re.findall(r'github\.com/([a-zA-Z0-9-]+)', text, re.IGNORECASE)
    
    if len(found_urls) >= 2:
        u1, u2 = found_urls[0], found_urls[1]
    else:
        words = [w.strip("@/,") for w in text.split() if not w.lower().startswith("сравн")]
        targets = [w for w in words if len(w) > 1 and "github.com" not in w]
        if len(targets) < 2:
            return "⚠️ Укажи два профиля! Пример: `сравни https://github.com/user1 https://github.com/user2`"
        u1, u2 = targets[0], targets[1]

    s1, err1 = fetch_github_profile_stats(u1)
    s2, err2 = fetch_github_profile_stats(u2)

    if err1 or err2 or not s1 or not s2:
        prompt = f"Сравни двух разработчиков GitHub: {u1} и {u2}. Вынеси саркастичный вердикт, кто из них круче и почему."
        return ask_text_ai(telegram_username, prompt, user_id, bypass_history=True)

    langs1 = ", ".join(sorted(s1['languages'], key=s1['languages'].get, reverse=True)[:5]) or "Не указаны"
    langs2 = ", ".join(sorted(s2['languages'], key=s2['languages'].get, reverse=True)[:5]) or "Не указаны"

    ai_prompt = (
        f"Сравни двух разработчиков на GitHub на основе их профилей:\n\n"
        f"Разработчик 1 ({s1['username']}): {s1['public_repos']} репозиториев, {s1['followers']} фоловеров. Био: '{s1['bio']}'. Топ языков: {langs1}.\n"
        f"Разработчик 2 ({s2['username']}): {s2['public_repos']} репозиториев, {s2['followers']} фоловеров. Био: '{s2['bio']}'. Топ языков: {langs2}.\n\n"
        f"Проанализируй эти данные и дай жесткий, саркастичный и смешной вердикт: кто из них круче, кто зашкварнее, загноби их за Си/С++/Python если есть, занизь за отсутствие Rust или похвали если пишут на Rust."
    )

    return ask_text_ai(telegram_username, ai_prompt, user_id, bypass_history=True)
