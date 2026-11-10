# RoadMap — система моніторингу стану доріг та ремонтних робіт

Командний проєкт з дисципліни «Проєктування інформаційних систем», НУ «Львівська політехніка», гр. ОІ-31, ОІ-33.

Система об'єднує комунальні служби, дорожню поліцію та підрядників навколо єдиної карти стану доріг міста. Водії повідомляють про ями, аварії й перешкоди прямо з карти, сигнал одразу надходить відповідальній службі, а водій отримує зворотний зв'язок про результат.

## Команда

| Роль | Учасник | GitHub |
|---|---|---|
| Керівник проєкту / Scrum-майстер | | |
| Бізнес-аналітик | | |
| Архітектор системи | | |
| Data Governance Engineer | | |
| Розробник (Backend / Integration) | | |
| Розробник (Frontend / UX) | | |
| QA / Тестувальник | | |

## Стек

- **Бекенд:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 + GeoAlchemy2, Alembic
- **База даних:** PostgreSQL 16 + PostGIS 3
- **Фронтенд:** React + TypeScript, Vite, Leaflet + OpenStreetMap (PWA)
- **Інфраструктура:** Docker Compose, GitHub Actions
- **Якість коду:** pytest, Ruff; ESLint, Prettier

## Структура репозиторію

```
road-monitoring-system/
├── backend/                 # API на FastAPI (модульний моноліт)
│   ├── app/
│   │   ├── main.py          # створення застосунку, підключення модулів
│   │   ├── core/            # налаштування, БД, безпека (JWT, RBAC), шина подій
│   │   ├── modules/         # кожен модуль: router · service · repository · models · schemas
│   │   │   ├── users/           # користувачі, ролі, вхід
│   │   │   ├── reports/         # заявки, статуси, підтвердження
│   │   │   ├── routing/         # правила й геозони
│   │   │   ├── dedup/           # пошук дублікатів, пріоритет
│   │   │   ├── work_orders/     # підрядні роботи
│   │   │   ├── notifications/   # WebSocket і email
│   │   │   ├── audit/           # журнал змін
│   │   │   └── admin/           # довідники
│   │   └── integrations/    # адаптер міських систем (мок і реальний)
│   ├── migrations/          # міграції Alembic
│   ├── tests/               # тести pytest
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/                # React-застосунок (PWA)
├── docs/                    # документація, ADR, діаграми
├── docker-compose.yml       # запуск усього однією командою
├── .env.example             # шаблон налаштувань
└── CONTRIBUTING.md          # правила гілок, комітів і code review
```

Шари всередині модуля: **router** (прийом запиту, перевірка прав) → **service** (бізнес-правила) → **repository** (запити до БД). Модулі не звертаються до таблиць одне одного напряму.

## Як запустити

Потрібно: [Git](https://git-scm.com/) і [Docker Desktop](https://www.docker.com/products/docker-desktop/).

1. Склонуй репозиторій і відкрий папку в VS Code.
2. Створи файл налаштувань із шаблону (один раз):
   - Windows (cmd): `copy .env.example .env`
   - macOS / Linux: `cp .env.example .env`
3. Запусти:
   ```
   docker compose up --build
   ```
4. Перевірка:
   - http://localhost:8000/docs — документація API (Swagger)
   - http://localhost:8000/api/v1/health — має повернути `{"status": "ok"}`
   - http://localhost:8000/api/v1/health/db — має показати версію PostGIS

Зупинити: `Ctrl + C`, потім `docker compose down`. Стерти дані БД повністю: `docker compose down -v`.

## База даних

PostgreSQL 16 + PostGIS. Схема створюється міграціями Alembic автоматично під час `docker compose up` (`alembic upgrade head`):

| Міграція | Що робить |
|---|---|
| `0001` | вмикає PostGIS |
| `0002` | таблиці за ER-моделлю (15 таблиць), обмеження CHECK/UNIQUE, геоіндекси, тригери незмінності журналів |
| `0003` | довідники: ролі, типи проблем, служби, межа міста, правила маршрутизації, політики доступу (RBAC) |

Підключитися до БД з комп'ютера (DBeaver, pgAdmin): `localhost:5432`, база/користувач/пароль — з `.env`.

## Вхід і демо-користувачі

- `POST /api/v1/auth/register` — реєстрація водія (обов'язкові згоди `terms` і `personal_data`).
- `POST /api/v1/auth/login` — вхід, повертає JWT-токен (поле `username` — це email).
- `GET /api/v1/auth/me` — поточний користувач.

Створити демо-акаунти для кожної ролі (пароль `Demo12345`):

```
docker compose exec api python -m app.scripts.create_demo_users
```

| Email | Роль |
|---|---|
| driver@roadmap.local | Водій |
| dispatcher@roadmap.local | Диспетчер комунальної служби |
| operator@roadmap.local | Оператор комунальної служби |
| police@roadmap.local | Дорожня поліція |
| contractor@roadmap.local | Підрядник |
| admin@roadmap.local | Адміністратор |
| dg@roadmap.local | Data Governance |

У Swagger (`/docs`) натисни **Authorize**, введи email у поле `username` і пароль — далі всі запити йдуть з токеном.

Тести працюють з окремою базою `roadmap_test`, яка створюється автоматично.

### Корисні команди

```
docker compose exec api pytest                                  # тести
docker compose exec api ruff check .                            # перевірка стилю
docker compose exec api alembic revision --autogenerate -m "опис"   # нова міграція
docker compose exec api alembic upgrade head                    # застосувати міграції
```

## Як працюємо з Git

Коротко: у `main` напряму не пишемо. Кожна задача робиться в окремій гілці, потім відкривається Pull Request, і після рев'ю він зливається в `main`. Детально описано в [CONTRIBUTING.md](CONTRIBUTING.md).
