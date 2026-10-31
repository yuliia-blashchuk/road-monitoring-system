
# RoadMap — Frontend

Фронтенд системи моніторингу стану доріг і ремонтних робіт RoadMap.

## Технологічний стек

- React + TypeScript
- Vite
- React Router
- Leaflet + React Leaflet
- OpenStreetMap
- ESLint + Prettier

PWA-функціональність передбачена архітектурою проєкту
та буде реалізована на наступних етапах.

## Запуск проєкту

Для роботи потрібні Node.js та npm.

1. Перейти в папку frontend:

```bash
cd frontend
```

2. Встановити залежності:

```bash
npm install
```

3. Запустити застосунок:

```bash
npm run dev
```

Застосунок буде доступний за адресою:
http://localhost:5173/

## Перевірка коду

Збірка проєкту:

```bash
npm run build
```

Перевірка ESLint:

```bash
npm run lint
```

Перевірка TypeScript:

```bash
npx tsc -b
```

## Структура проєкту

- `src/App.tsx` — маршрути та сторінки.
- `src/components/AppLayout.tsx` — шапка, навігація та основна область.
- `src/App.css` — стилі компонентів.
- `src/index.css` — глобальні стилі.

## Реалізовано в KAN-28

- Ініціалізація React + TypeScript + Vite.
- Базовий роутинг.
- Компонент AppLayout.
- Адаптивне оформлення інтерфейсу.
- Підключення Leaflet та OpenStreetMap.
- Початкові сторінки карти, звернень і входу.

Сторінки звернень та авторизації наразі є заглушками.
Інтеграція з API буде виконуватися на наступних етапах.

## Backend API

Базова адреса API:
http://localhost:8000/api/v1

Документація Swagger:
http://localhost:8000/docs
```
