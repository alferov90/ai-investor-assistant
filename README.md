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
- AI-анализ акций (OpenAI или rule-based fallback)
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
```

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
| GET | `/api/stocks/{ticker}/analysis` | AI-анализ |

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
