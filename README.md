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
├── scripts/windows/         # запуск бекенду без Docker (.bat)
├── docker-compose.yml       # запуск усього однією командою
├── .env.example             # шаблон налаштувань
└── CONTRIBUTING.md          # правила гілок, комітів і code review
```

Шари всередині модуля: **router** (прийом запиту, перевірка прав) → **service** (бізнес-правила) → **repository** (запити до БД). Модулі не звертаються до таблиць одне одного напряму.

## Як запустити

Є два рівноцінні способи. Код однаковий, різниця лише в тому, чим запускати; для фронтенду бекенд в обох випадках доступний за адресою `http://localhost:8000/api/v1`.

### Спосіб A — Docker (одна програма, все автоматично)

Потрібно: [Git](https://git-scm.com/) і [Docker Desktop](https://www.docker.com/products/docker-desktop/).

1. Створи файл налаштувань із шаблону (один раз):
   - Windows (cmd): `copy .env.example .env`
   - macOS / Linux: `cp .env.example .env`
2. Запусти:
   ```
   docker compose up --build
   ```
3. Демо-акаунти: `docker compose exec api python -m app.scripts.create_demo_users`

Зупинити: `Ctrl + C`, потім `docker compose down`. Стерти дані БД повністю: `docker compose down -v`.

### Спосіб B — без Docker (Windows)

Потрібно:
- [Python 3.12+](https://www.python.org/downloads/) — під час встановлення постав галочку **Add python.exe to PATH**;
- [PostgreSQL](https://www.postgresql.org/download/windows/) з PostGIS — після встановлення PostgreSQL запуститься Stack Builder: вибери свій сервер → **Spatial Extensions** → **PostGIS**. Запам'ятай пароль користувача `postgres`.

Далі двічі клацни по файлах у папці `scripts\windows`:

| Файл | Що робить |
|---|---|
| `1-setup-backend.bat` | перший раз створить `.env` і відкриє його — впиши `POSTGRES_USER=postgres` і свій пароль, збережи й запусти скрипт ще раз; далі встановить бібліотеки, створить базу й таблиці |
| `2-run-backend.bat` | запускає бекенд на http://localhost:8000 |
| `3-test-backend.bat` | запускає автотести |
| `4-create-demo-users.bat` | створює демо-акаунти |

### Перевірка (для обох способів)

- http://localhost:8000/docs — документація API (Swagger)
- http://localhost:8000/api/v1/health/db — має показати версію PostGIS

### Для фронтенду

- Адреса API: `http://localhost:8000/api/v1` (краще винести у змінну `VITE_API_URL`, щоб потім легко змінити на адресу сервера).
- Дозволені адреси фронтенду задаються в `.env` → `CORS_ORIGINS` (за замовчуванням `http://localhost:5173`).
- Вхід: `POST /auth/login` (форма `username` = email, `password`) → `access_token`; далі в кожному запиті заголовок `Authorization: Bearer <access_token>`.
- Які кнопки показувати: `GET /auth/me/permissions`.

### Корисні команди

```
docker compose exec api pytest                                  # тести
docker compose exec api ruff check .                            # перевірка стилю
docker compose exec api alembic revision --autogenerate -m "опис"   # нова міграція
docker compose exec api alembic upgrade head                    # застосувати міграції
```

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

Без Docker — двічі клацнути `scripts\windows\4-create-demo-users.bat`.

| Email | Роль |
|---|---|
| driver@roadmap.local | Водій |
| dispatcher@roadmap.local | Диспетчер комунальної служби Залізничного району |
| dispatcher2@roadmap.local | Диспетчер комунальної служби Шевченківського району |
| operator@roadmap.local | Оператор комунальної служби Залізничного району |
| police@roadmap.local | Дорожня поліція |
| contractor@roadmap.local | Підрядник |
| admin@roadmap.local | Адміністратор |
| dg@roadmap.local | Data Governance |

У Swagger (`/docs`) натисни **Authorize**, введи email у поле `username` і пароль — далі всі запити йдуть з токеном.

## Права доступу (RBAC)

Права задаються таблицею `access_policy` (матриця «роль × ресурс × дія», п. 3.4 звіту) і перевіряються на сервері для кожного запиту:

```python
from typing import Annotated
from fastapi import Depends
from app.core.access_control import AccessContext, require

ChangeStatus = Annotated[AccessContext, Depends(require("report", "change_status"))]

@router.patch("/reports/{report_id}/status")
async def change_status(report_id: int, ctx: ChangeStatus, ...):
    await ctx.ensure_target(entity_id=report_id, service_ids=[report.service_id, report.copy_service_id])
```

- немає політики для ролі → **403** і запис `ACCESS_DENIED` у журнал аудиту;
- `ctx.scope` — область дії (`own`, `service`, `all`, `public`), `ensure_target()` перевіряє конкретний запис;
- `app.core.classification.filter_request()` прибирає з відповіді поля, які роль бачити не повинна.

Тести працюють з окремою базою `roadmap_test`, яка створюється автоматично.

## Створення заявки (KAN-57)

`POST /api/v1/reports` — лише для водія, формат `multipart/form-data`:

| Поле | Обов'язкове | Правило |
|---|---|---|
| `problem_type` | так | код з `GET /api/v1/problem-types` (`pothole`, `obstacle`, …) |
| `latitude`, `longitude` | так | WGS84; точка в межах міста, інакше 422 «Ділянка не обслуговується» |
| `comment` | ні | до 300 символів |
| `photos` | ні | до 3 файлів JPEG / PNG / WebP, кожен до 5 МБ; EXIF видаляється |
| `media_sharing_consent` | якщо є фото або коментар | `true` — згода передати службі фото й коментар |
| `address`, `device_created_at` | ні | адреса; час створення офлайн-заявки (не старше 24 год) |

Відповіді: **201** з `number`, `status`, `priority`, `service` і `copy_service` (визначає маршрутизація, див. нижче), **422** з назвою поля в `detail[0].loc`, **403** без згоди на обробку персональних даних, **429** після 10 заявок за годину.

Приклад для фронтенду:

```ts
const body = new FormData()
body.append('problem_type', 'pothole')
body.append('latitude', String(lat))
body.append('longitude', String(lng))
body.append('comment', comment)
body.append('media_sharing_consent', 'true')
files.forEach((file) => body.append('photos', file))

await fetch(`${API_URL}/reports`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` }, // Content-Type не задавати: браузер додасть сам
  body,
})
```

Фото зберігаються в папці `backend/media` (налаштування `MEDIA_DIR`); у продуктиві замість неї буде MinIO через той самий інтерфейс `app/core/storage.py`.

## Маршрутизація заявок (KAN-58)

Під час створення заявки служба, служба-копія й початковий пріоритет визначаються за таблицею `routing_rule`: правило підходить, якщо збігається тип проблеми і точка лежить у зоні служби (`service.zone`). Правила зберігаються в БД, тому нове правило додається без зміни коду; список видно адміністратору в `GET /api/v1/admin/routing-rules`.

| Тип | Служба | Копія | Пріоритет |
|---|---|---|---|
| Яма | комунальна служба району | — | середній |
| Пошкоджене покриття | комунальна служба району | — | низький |
| Несправний світлофор | комунальна служба району | — | високий |
| Інше | комунальна служба району | — | низький |
| Аварія (ДТП) | дорожня поліція | комунальна служба району | критичний |
| Перешкода | дорожня поліція | комунальна служба району | високий |

Місто поділено на дві демонстраційні зони: Залізничний район (захід, довгота до 24.03) і Шевченківський (схід). Якщо правила немає, заявка лишається без служби (`service = null`) і потрапляє адміністратору.

## Як працюємо з Git

Коротко: у `main` напряму не пишемо. Кожна задача робиться в окремій гілці, потім відкривається Pull Request, і після рев'ю він зливається в `main`. Детально описано в [CONTRIBUTING.md](CONTRIBUTING.md).
