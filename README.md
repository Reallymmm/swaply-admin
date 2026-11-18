# Swaply Web

Структура проекта:

    swaply-web/
      backend/    - сервер (FastAPI + PostgreSQL), отдаёт данные по /api/...
      frontend/   - админка (HTML + CSS + JS), берёт данные у бэкенда

Запуск (Windows, PowerShell):

    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env        (открыть .env и вписать пароль от PostgreSQL)
    uvicorn app.main:app --reload

Открыть в браузере: http://127.0.0.1:8000
Документация API:   http://127.0.0.1:8000/docs

Перед первым запуском в PostgreSQL нужно создать пустую базу swaply.
Бэкенд сам отдаёт и папку frontend, поэтому отдельно фронт запускать не нужно.

Почта для регистрации в приложении:

    Новый пользователь вводит имя, email и пароль, на почту приходит 6-значный код,
    после ввода кода аккаунт создаётся. Настройки почты (SMTP_*) лежат в backend/.env,
    пример - в backend/.env.example. Пока SMTP_HOST пустой, письма не отправляются,
    а код печатается в окне, где запущен uvicorn.
