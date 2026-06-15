# AI Investor Assistant

Production-ready SaaS для управления инвестиционным портфелем с AI-анализом акций.

## Стек

| Слой | Технологии |
|------|------------|
| Backend | FastAPI, SQLAlchemy, Alembic, JWT |
| Frontend | HTML, TailwindCSS, Vanilla JS |
| Infra | Docker Compose, PostgreSQL, Redis |

## Возможности

- Регистрация и авторизация (JWT)
- Dashboard с P/L и топ-позициями
- Портфель: добавление, редактирование, удаление тикеров
- Котировки: Finnhub / Yahoo / Stooq (fallback)
- Telegram Bot: /analyze, /portfolio, /watchlist, /alerts, утренний дайджест
- Кэширование котировок в Redis

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

| Страница | URL |
|----------|-----|
| Главная | http://localhost:8000 |
| Регистрация | http://localhost:8000/register |
| Dashboard | http://localhost:8000/dashboard |
| Портфель | http://localhost:8000/portfolio |
| Анализ | http://localhost:8000/analysis |
| API Docs | http://localhost:8000/api/docs |

## Переменные окружения

```env
POSTGRES_USER=investor
POSTGRES_PASSWORD=change-me-in-production
POSTGRES_DB=investor
SECRET_KEY=change-me-use-openssl-rand-hex-32
OPENAI_API_KEY=          # опционально, для GPT-анализа
OPENAI_MODEL=gpt-4o-mini
FINNHUB_API_KEY=          # бесплатно: https://finnhub.io — рекомендуется для VPS в РФ
YAHOO_PROXY_URL=          # опционально, если нужен Yahoo
```

## Котировки на VPS (РФ)

Yahoo Finance часто **недоступен** с российских серверов. Варианты:

1. **Finnhub** (рекомендуется) — бесплатный ключ на [finnhub.io](https://finnhub.io):
   ```env
   FINNHUB_API_KEY=your_key
   ```
2. **Stooq** — используется автоматически как fallback (только цена)
3. **Yahoo через прокси**:
   ```env
   YAHOO_PROXY_URL=http://proxy:port
   ```

## Telegram Bot

1. Создайте бота в [@BotFather](https://t.me/BotFather)
2. Укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_USERNAME` в `.env`
3. Dashboard → «Подключить Telegram» → нажмите Start в боте

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие / подключение аккаунта |
| `/help` | Все команды |
| `/analyze NVDA` | AI-анализ акции |
| `/portfolio` | Ваш портфель |
| `/digest` | Дайджест портфеля сейчас |
| `/watchlist` | Список наблюдения |
| `/watchadd AAPL` | Добавить в watchlist |
| `/watchdel AAPL` | Удалить из watchlist |
| `/alerts` | Список алертов |
| `/alert AAPL above 150` | Создать алерт |
| `/alertdel 3` | Удалить алерт по ID |

Утренний дайджест отправляется автоматически в **09:00 МСК** (настраивается через `TELEGRAM_DIGEST_HOUR` UTC в `.env`).

## API

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация |
| POST | `/api/auth/login` | Вход |
| GET | `/api/auth/me` | Текущий пользователь |
| GET | `/api/portfolio` | Список позиций |
| POST | `/api/portfolio` | Добавить тикер |
| PATCH | `/api/portfolio/{id}` | Обновить позицию |
| DELETE | `/api/portfolio/{id}` | Удалить позицию |
| GET | `/api/portfolio/dashboard` | Статистика dashboard |
| GET | `/api/stocks/{ticker}` | Данные акции (Yahoo Finance) |
| GET | `/api/stocks/{ticker}/quote` | Котировка |
| GET | `/api/stocks/{ticker}/analysis` | AI-анализ (OpenAI) |
| GET | `/api/telegram/status` | Статус Telegram |
| POST | `/api/telegram/link` | Ссылка для подключения бота |
| DELETE | `/api/telegram/disconnect` | Отключить Telegram |

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Запустите postgres и redis локально или через docker compose up postgres redis -d
alembic upgrade head
uvicorn app.main:app --reload
```

## Деплой на VPS

**Не передавайте пароли в чат.** Используйте SSH-ключ.

### 1. Один раз на сервере (под `dev`)

```bash
# Публичный ключ с вашего Mac (скопируйте вывод и вставьте на сервер)
cat ~/.ssh/id_ed25519.pub

# На VPS:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ВАШ_ПУБЛИЧНЫЙ_КЛЮЧ" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Клонировать проект (если ещё нет)
git clone git@github.com:alferov90/ai-investor-assistant.git ~/ai-investor-assistant
cd ~/ai-investor-assistant
cp .env.example .env && nano .env
docker compose up -d --build
```

### 2. Один раз на Mac

```bash
cp .deploy.env.example .deploy.env
nano .deploy.env   # DEPLOY_HOST = IP или hostname VPS
chmod +x scripts/deploy.sh
ssh dev@ВАШ_IP "echo ok"   # проверка входа без пароля
```

### 3. После каждого изменения

```bash
git push origin main
./scripts/deploy.sh          # только pull + docker на сервере
./scripts/deploy.sh --push   # push + deploy
```

### Автодеплой через GitHub Actions

В Settings → Secrets добавьте: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (приватный ключ).  
При каждом push в `main` сервер обновится сам.

## Структура проекта

```
ai-investor-assistant/
├── alembic/              # Миграции БД
├── app/
│   ├── routers/          # API endpoints
│   ├── services/         # Бизнес-логика (акции, AI)
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   └── ...
├── static/               # Frontend
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```
