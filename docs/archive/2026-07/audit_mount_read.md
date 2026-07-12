# Аудит mount read — 2026-07-04

## 0. Git
```
ahead=1, behind=0
```

## 1. Что alembic реально видит

```
script_location = migrations    # → /app/migrations/versions/

alembic history:
  <base> → ca16 → da0a → 4afd → b111 → c2a1 → 0479653cd24b (head)
```

0479 видна в history ✅ — alembic читает КОНТЕЙНЕРНУЮ ФС.

## 2. Маркер-тест (bind-mount)

```
HOST: echo test > migrations/versions/.__marker     ✓ (создан)
CTN:  cat /app/migrations/versions/.__marker        ✗ No such file
```

**Bind-mount МЁРТВ.** Хост-файлы не видны в контейнере. Контейнер читает снапшот образа (COPY . . при сборке) или overlay-слой, не связанный с хостом.

## 3. docker compose cp

```
docker compose cp /tmp/test.py worker:/app/migrations/versions/.__cptest → Copied ✓
cat в контейнере → виден ✓
```

**`docker compose cp` работает.** Это прямой файловый трансфер в работающий контейнер, обходящий bind-mount.

## 4. ВЫВОД

### Путь 1 (рабочий): `docker compose cp` + `alembic upgrade`
1. Создать правильную миграцию на хосте
2. `docker compose cp migrations/versions/<file>.py worker:/app/migrations/versions/`
3. `docker compose exec worker alembic upgrade head`
4. ✅

### Путь 2 (мёртвый): писать на хост и ждать синка
Bind-mount не работает → хост-файлы не видны контейнеру. ❌

### Путь 3 (радикальный): пересоздать контейнер с фиксом mount
Требует `docker compose down/up worker` → стоп прод-воркера. Отложено.
