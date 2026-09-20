# Sosal AI — Telegram Bot

ИИ-ассистент для Telegram на базе Google AI Studio (Gemini / Gemma), интегрированный с PostgreSQL, Pollinations AI и GitHub API.

## Возможности
* **Мультимодельный Текст:** Поддержка Gemini Flash Lite и Gemma (с контекстной памятью диалога и автоматическим переключением моделей).
* **Мультимедиа & Зрение:** Анализ изображений, стикеров, GIF, видео и документов.
* **Анализ кода (`/gitv`):** Скачивание, парсинг структуры и ревью публичных GitHub-репозиториев.
* **Сравнение разработчиков:** Анализ и сравнение GitHub-профилей пользователей.
* **Генерация изображений (`/pic`):** Генерация артов через Pollinations AI (Flux, ZImage) с автоматическим переводом и расширением промпта.
* **Управление лимитами:** Ограничение daily-запросов и защита от флуда с хранением данных в PostgreSQL.

## Стек технологий
* **Язык:** Python 3.10+
* **Фреймворк:** `pyTelegramBotAPI`
* **База данных:** PostgreSQL (`psycopg2`)
* **AI Engine:** Google AI Studio API (Gemini 3.1 Flash / Gemma 4)
* **Деплой:** Поддержка Render.com (Web Service + Secret Files)

## Быстрый старт

1. **Клонируйте репозиторий:**
  ```bash
    git clone https://github.com/ktoto42-oss/sosal-ai-bot
    cd sosal-ai-bot
  ```
  
2. **Установите зависимости:**
  ```bash
    pip install -r requirements.txt
  ```
  
3. **Настройте переменные окружения:**
  Создайте файл .env или добавьте переменные в панели вашего хостинга:
  ```bash
    TELEGRAM_TOKEN=your_telegram_bot_token
    GOOGLE_API_KEY=your_google_ai_studio_key
    DATABASE_URL=postgresql://user:password@host:5432/dbname
    ADMIN_ID=123456789
    PORT=10000
  ```
  
4. **Системный промпт (Secret File):**
   Создайте файл system_prompt.txt в корне проекта с вашей инструкцией для бота (при деплое на Render загрузите его в раздел Secret Files).

5. **Запустите бота:**
  ```bash
    python main.py
  ```
  
