# Swaply Admin (бэкенд + админка)

Серверная часть Swaply, платформы для обмена вещами без денег. Здесь живут:

- **API для мобильного приложения** (`/api/m/...`): регистрация с кодом на почту, объявления, чаты, избранное, отзывы, уведомления;
- **панель администратора** (обычные HTML/JS-страницы): модерация объявлений, пользователи и блокировки, апелляции, отзывы, категории;
- **PostgreSQL** с данными и папка `uploads` с фотографиями.

Мобильное приложение лежит в отдельном репозитории: `swaply-mobile`.

**Стек:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, Docker.

## Структура

```
swaply-admin/
  backend/
    app/
      main.py        - приложение FastAPI, вход в админку, API админки
      mobile.py      - API мобильного приложения (/api/m/...)
      models.py      - таблицы базы данных
      mailer.py      - отправка кодов на почту через Brevo
      db.py          - подключение к базе
      security.py    - хэширование паролей и токены
    requirements.txt - зависимости Python
    .env.example     - пример настроек сервера
    uploads/         - загруженные фото (создаётся сама, в Git не попадает)
  frontend/          - страницы админки (HTML, CSS, JS)
  Dockerfile         - образ сервера
  docker-compose.yml - сервер + PostgreSQL одной командой
  .env.example       - пример настроек базы для Docker
```

## Быстрый старт через Docker (рекомендуется)

Нужен установленный [Docker Desktop](https://www.docker.com/products/docker-desktop/). Python и PostgreSQL ставить не нужно.

**1. Настрой сервер.** Скопируй пример и открой файл `backend/.env`:

```
copy backend\.env.example backend\.env
```

| Переменная | Что это |
|---|---|
| `ADMIN_USER` | Логин для входа в админку (по умолчанию `admin`) |
| `ADMIN_PASSWORD` | Пароль админки. **Обязателен:** без него сервер не запустится |
| `BREVO_API_KEY` | Ключ API Brevo для отправки кодов на почту (см. раздел «Почта») |
| `BREVO_SENDER_EMAIL` | Подтверждённый в Brevo адрес отправителя |
| `BREVO_SENDER_NAME` | Имя отправителя в письме (по умолчанию `Swaply`) |
| `DATABASE_URL` | Нужен только при запуске без Docker. В Docker адрес базы задаёт `docker-compose.yml` |

**2. (Необязательно) Настрой пароль базы.** По умолчанию база создаётся с пользователем `swaply` и паролем `swaply_pass`. Чтобы задать свой, создай в корне проекта файл `.env`:

```
copy .env.example .env
```

и впиши `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.

> Эти значения применяются только при **первом** создании базы. Если поменять пароль позже, база сохранит старый. Чтобы начать с чистой базы: `docker compose down -v` (это **удалит все данные**).

**3. Запусти:**

```
docker compose up -d --build
```

**4. Открой в браузере:** http://localhost:8000

Браузер спросит логин и пароль: это `ADMIN_USER` и `ADMIN_PASSWORD` из `backend/.env`. Документация API: http://localhost:8000/docs (тот же логин и пароль).

### Полезные команды

| Команда | Что делает |
|---|---|
| `docker compose logs -f web` | Смотреть логи сервера (там же печатаются коды, если почта не настроена) |
| `docker compose down` | Остановить, данные сохранятся |
| `docker compose up -d --build` | Пересобрать и запустить после изменений в коде |
| `docker compose down -v` | Остановить и **удалить базу** |
| `docker compose exec db pg_dump -U swaply -Fc -f /tmp/backup.dump swaply` и затем `docker compose cp db:/tmp/backup.dump ./backup.dump` | Резервная копия базы в файл `backup.dump` (если менял `POSTGRES_USER` или `POSTGRES_DB`, подставь свои) |

Код копируется в образ при сборке, поэтому после правок в `backend/` или `frontend/` нужна пересборка (`--build`). Фото из `backend/uploads` хранятся на твоём компьютере и переживают пересборку.

## Запуск без Docker (Windows, PowerShell)

Нужны Python 3.12+ и PostgreSQL. Создай в PostgreSQL пустую базу `swaply`.

```
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Открой `backend/.env`, впиши `DATABASE_URL` (логин и пароль от своего PostgreSQL), `ADMIN_PASSWORD` и по желанию настройки Brevo. Затем запусти **из папки `backend`**:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Если запустить из корня проекта, будет ошибка `No module named 'app'`.

Таблицы создаются автоматически при старте сервера, миграции делать не нужно.

## Почта: коды подтверждения при регистрации

Регистрация в приложении идёт в два шага: человек вводит имя, email и пароль, на почту приходит 6-значный код, после ввода кода создаётся аккаунт. Пока почта не подтверждена, аккаунта нет.

- Код действует **10 минут**, ошибиться можно **5 раз**, новый код можно запросить раз в **60 секунд**.
- Письма отправляются через [Brevo](https://www.brevo.com/) по HTTPS (порт 443), поэтому это работает и там, где закрыты почтовые порты SMTP.

**Как настроить Brevo:**

1. Зарегистрируйся в Brevo. На бесплатном тарифе есть дневной лимит писем, для начала его хватает.
2. Добавь и подтверди адрес отправителя (раздел Senders в кабинете Brevo). Этот адрес пойдёт в `BREVO_SENDER_EMAIL`. Brevo шлёт на него письмо со ссылкой подтверждения.
3. Создай ключ API (раздел SMTP & API, вкладка API keys). Ключ пойдёт в `BREVO_API_KEY`.
4. Перезапусти сервер, чтобы он прочитал новый `.env`: `docker compose up -d --force-recreate web`.

Подробности по API Brevo: https://developers.brevo.com/docs/send-a-transactional-email

Если `BREVO_API_KEY` пустой, письма не отправляются, а код печатается в логах сервера: `docker compose logs -f web`. Так удобно проверять регистрацию на этапе разработки.

## Как подключить мобильное приложение

Приложение обращается к серверу по адресу из `src/config.js` в репозитории `swaply-mobile`. Впиши туда IP компьютера, где запущен сервер, и порт 8000:

```js
export const API_URL = "http://192.168.0.105:8000";
```

IP смотри командой `ipconfig` (строка «IPv4-адрес»). Телефон и компьютер должны быть в одной Wi-Fi сети, а брандмауэр Windows должен пропускать порт 8000.

## Админка

Страницы панели: обзор со статистикой, объявления (одобрить, заблокировать), пользователи (блокировка с причиной, изменение профиля), апелляции на блокировки, отзывы (скрыть, удалить), категории.

Вход защищён логином и паролем (`ADMIN_USER` / `ADMIN_PASSWORD`). Без входа открыты только API мобильного приложения (`/api/m/...`), загруженные фото (`/uploads/...`) и список категорий.

## API мобильного приложения

Все пути начинаются с `/api/m`. Подробная документация с примерами: `/docs`.

| Раздел | Пути |
|---|---|
| Регистрация и вход | `POST /register`, `POST /register/confirm`, `POST /register/resend`, `POST /login` |
| Профиль | `GET /me`, `PUT /me/city`, `POST` и `DELETE /me/avatar`, `GET /users/{id}` |
| Объявления | `GET /feed`, `GET /listings/{id}`, `POST /listings`, `PUT /listings/{id}`, `GET /my-listings`, фото |
| Избранное и отзывы | `GET /favorites`, `POST /favorites/{id}`, `POST /users/{id}/reviews` |
| Чаты | `POST /chats`, `GET /chats`, `GET /chats/{id}`, `POST /chats/{id}/messages` |
| Уведомления | `GET /notifications`, `GET /notifications/history`, `POST /notifications/read` |
| Блокировки | `POST /appeals`, `POST /appeals/status` |

Авторизация в приложении идёт по токену: заголовок `Authorization: Bearer <токен>`, токен выдаётся при входе и регистрации.

## Безопасность

- Файл `backend/.env` содержит пароли и ключи. Он в `.gitignore`, не отправляй его в Git и не пересылай другим.
- Смени `ADMIN_PASSWORD` и пароль базы на свои, прежде чем открывать сервер из интернета.
- Для публичного сервера поставь перед ним HTTPS (например, через nginx или Caddy): без него пароли и токены ходят по сети открытым текстом.

## Частые проблемы

| Проблема | Решение |
|---|---|
| `ADMIN_PASSWORD is not set` | Заполни `ADMIN_PASSWORD` в `backend/.env` |
| `env file ... backend/.env not found` | Создай файл: `copy backend\.env.example backend\.env` |
| `No module named 'app'` | Запускай `uvicorn` из папки `backend`, а не из корня проекта |
| Порт 8000 занят | Закрой другую программу или поменяй порт слева в `ports` в `docker-compose.yml`, например `"8001:8000"` |
| Код не приходит на почту | Проверь `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` и что отправитель подтверждён в Brevo. Причину покажут логи: `docker compose logs web` |
| Поменял пароль базы, а сервер не подключается | База помнит старый пароль. Верни его или пересоздай базу: `docker compose down -v` (данные удалятся) |
| Телефон не видит сервер | Проверь IP в `config.js`, что оба устройства в одной сети и что брандмауэр пропускает порт 8000 |
