# CLAUDE-2.md — Фаза «Админка на shadcn/ui»

Дата: 2026-06-29
Статус: 🔨 В разработке — Фазы 1-6 фронтенда завершены

---

## Цель

Переписать админ-панель LeadHunter с SQLAdmin на современный стек:
- **Фронтенд:** Vite + React + shadcn/ui + Tailwind (НЕ Next.js — принято решение на grilling-сессии)
- **Бэкенд:** FastAPI (тот же, на порту 8001) как REST API
- **Live-чат:** WebSocket через Redis pub/sub (уже реализован)

---

## План

### ✅ Шаг 1: Создать Vite + React проект

```bash
npm create vite@latest admin-panel -- --template react-ts
cd admin-panel
npm install react-router-dom @tanstack/react-query chart.js react-chartjs-2
npm install tailwindcss @tailwindcss/vite
npx shadcn@latest init  # Nova preset, neutral base, CSS variables
npx shadcn@latest add button card table dialog input tabs sheet sidebar pagination scroll-area avatar badge label textarea select skeleton dropdown-menu sonner separator
```

### ✅ Шаг 2: API-слой — REST ендпоинты

Создан `/app/admin/api/` с:

| Модуль | Путь | Описание |
|---|---|---|
| `auth.py` | `/api/auth/*` | Session-cookie логин/логаут |
| `crud.py` | `/api/{model}/*` | Генерический CRUD (countries, cities, segments, segment-keywords) |
| `users.py` | `/api/users/*` | Пользователи с фильтрацией |
| `stats.py` | `/api/stats/dashboard` | Статистика дашборда |
| `chat.py` | `/api/chat/*` + WS | Диалоги, история, WebSocket |
| `broadcast.py` | `/api/broadcast/*` | Статистика + отправка рассылки |
| `__init__.py` | `/api/channels/*` | Каналы с M:N (сегменты, города) |

### ✅ Шаг 3: Страницы админки

| Страница | Статус | Компоненты |
|---|---|---|
| `/login` | ✅ | Card, Input, Button |
| `/` (дашборд) | ✅ | 4 KPI Card, Line chart, Doughnut chart |
| `/users` | ✅ | Table, Input, Select, Badge, Pagination, DropdownMenu |
| `/catalog` | ✅ | Tabs (страны/города/сегменты/keywords), CRUD Table, Dialog |
| `/channels` | ✅ | Table, Input, Badge, Pagination |
| `/chat` | ✅ | ScrollArea, Avatar, Badge, Input, WebSocket |
| `/broadcast` | ✅ | Card, Textarea, Select, Badge, Toast |
| `/settings` | ✅ | Таблица тарифных лимитов, системная информация |

### ✅ Шаг 4: Аутентификация

- Session cookie через starlette `SessionMiddleware`
- FastAPI middleware проверяет `/api/*` (кроме `/api/auth/*`)
- React `AuthProvider` + `ProtectedRoute`
- Логин: `POST /api/auth/login` с admin_password из .env

### ✅ Шаг 5: Интеграция

- Vite build → `app/admin/static/`
- FastAPI раздаёт статику + API на порту 8001
- Vite proxy `/api` → `localhost:8001` в dev-режиме
- Сервис `dashboard` (порт 8002) удалён из docker-compose — всё на 8001

---

## Чек-лист

- [x] Vite + React проект создан, 20 shadcn/ui компонентов добавлены
- [x] REST API ендпоинты в FastAPI (10 роутеров)
- [x] Session-cookie аутентификация
- [x] Дашборд с 4 KPI и 2 графиками Chart.js
- [x] CRUD таблицы: users, catalog (4 таба), channels
- [x] Live-чат с WebSocket
- [x] Рассылка с фильтрацией
- [x] Страница настроек (тарифные лимиты)
- [x] Интеграция с docker-compose (dashboard удалён, всё на 8001)
- [x] Production build скопирован в app/admin/static/
- [ ] Тестирование в Docker
- [ ] Выпилить SQLAdmin после подтверждения

---

## Запуск через grill-me

В pi:
```
/agents → выбрать grill-me
```

Или напрямую:
```
grill-me "Распиши детальный план миграции админки LeadHunter с SQLAdmin на Next.js + shadcn/ui.
Проект: /opt/LeadHunter. Бэкенд FastAPI на порту 8001. БД PostgreSQL.
Нужно: аутентификация, CRUD таблицы, дашборд, live-чат, рассылки."
```
