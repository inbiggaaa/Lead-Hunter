# CLAUDE-2.md — Фаза «Админка на shadcn/ui»

Дата: 2026-06-29
Статус: ⏳ Планирование

---

## Цель

Переписать админ-панель LeadHunter с SQLAdmin на современный стек:
- **Фронтенд:** Next.js + shadcn/ui + Tailwind
- **Бэкенд:** FastAPI (тот же, на порту 8001) как REST API
- **Live-чат:** WebSocket через Redis pub/sub (уже реализован)

---

## План

### Шаг 1: Добавить shadcn/ui skill в pi

```bash
npx skills add https://github.com/shadcn/ui --skill shadcn
```

Это даст Claude Code знание shadcn/ui компонентов и паттернов.

### Шаг 2: Создать Next.js проект

```bash
npx create-next-app@latest admin-panel --typescript --tailwind --eslint --app --src-dir
cd admin-panel
npx shadcn@latest init
npx shadcn@latest add button card table dialog input tabs sheet sidebar
```

### Шаг 3: API-слой — добавить REST ендпоинты в FastAPI

Создать `/app/admin/api.py` с ендпоинтами:

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/users` | Список пользователей |
| GET | `/api/countries` | Страны |
| GET | `/api/cities` | Города |
| GET | `/api/segments` | Направления |
| GET | `/api/segment-keywords` | Keywords |
| GET | `/api/channels` | Каталог каналов |
| GET | `/api/subscriptions` | Подписки |
| GET | `/api/stats` | Статистика дашборда |
| GET | `/api/chat/dialogs` | Диалоги поддержки (уже есть) |
| GET | `/api/chat/history/{id}` | История чата (уже есть) |
| WS | `/api/chat/ws` | WebSocket чата (уже есть) |
| POST | `/api/broadcast` | Рассылка |

### Шаг 4: Страницы админки (shadcn/ui)

| Страница | Компоненты |
|---|---|
| `/` | Дашборд — KPI карточки (Card), графики (Chart.js) |
| `/users` | Таблица (Table), фильтры (Input), пагинация |
| `/catalog` | Табы стран/городов/сегментов (Tabs) |
| `/channels` | Таблица каналов |
| `/chat` | Чат — сайдбар (Sheet) + окно сообщений |
| `/broadcast` | Форма рассылки (Card, Textarea, Select) |
| `/settings` | Настройки тарифов/лимитов |

### Шаг 5: Аутентификация

- JWT токен через `/api/auth/login`
- Middleware проверки в Next.js
- Та же связка admin/admin_password из .env

### Шаг 6: Интеграция

- Next.js на порту 3000 (dev) / статический экспорт для прод
- nginx reverse proxy или отдельный порт 8001
- FastAPI API на том же порту 8001 с CORS

---

## Чек-лист

- [ ] shadcn/ui skill установлен
- [ ] Next.js проект создан, shadcn компоненты добавлены
- [ ] REST API ендпоинты в FastAPI
- [ ] Дашборд с KPI и графиками
- [ ] CRUD таблицы для всех моделей
- [ ] Live-чат с WebSocket
- [ ] Рассылка
- [ ] Аутентификация
- [ ] Интеграция с существующим docker-compose

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
