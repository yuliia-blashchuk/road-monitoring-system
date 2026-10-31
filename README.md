# RoadMap — система моніторингу стану доріг та ремонтних робіт

Командний проєкт з дисципліни «Проєктування інформаційних систем», НУ «Львівська політехніка», гр. ОІ-31.

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

### Корисні команди

```
docker compose exec api pytest                                  # тести
docker compose exec api ruff check .                            # перевірка стилю
docker compose exec api alembic revision --autogenerate -m "опис"   # нова міграція
docker compose exec api alembic upgrade head                    # застосувати міграції
```

## Як працюємо з Git

Коротко: у `main` напряму не пишемо. Кожна задача робиться в окремій гілці, потім відкривається Pull Request, і після рев'ю він зливається в `main`. Детально описано в [CONTRIBUTING.md](CONTRIBUTING.md).
