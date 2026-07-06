# Аудит механизма миграций — 2026-07-04

## 0. Git-санити
```
ahead=1 (сессионный лог), behind=0 ✓
```

## 1. Инструмент миграций

### Alembic (async PostgreSQL)
- Конфиг: `alembic.ini` (в корне), `script_location = migrations`
- Версии: `migrations/versions/` — 5 файлов
- ORM: `Base.metadata` из `app/db/models.py`, указан в `migrations/env.py:16` как `target_metadata`
- URL: `settings.database_url` (из `app/config.py`)

### Цепочка ревизий
```
ca16bab1a0cc  initial
da0a81014466  add idx_user_sub_lookup
4afd135dc3f1  dedup samui + add city constraint
b11187f388a9  add llm_decisions and feedback
c2a1d3b4e5f6  add content_hash to sent_log (2026-07-03)
```

### Типовой migration-файл
```python
# c2a1d3b4e5f6_add_content_hash_to_sent_log.py
revision: str = "c2a1d3b4e5f6"
down_revision: Union[str, None] = "b11187f388a9"

def upgrade() -> None:
    op.add_column("sent_log", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("idx_sent_log_content_dedup", "sent_log", ["user_id", "content_hash", "sent_at"])

def downgrade() -> None:
    op.drop_index("idx_sent_log_content_dedup", table_name="sent_log")
    op.drop_column("sent_log", "content_hash")
```

### ORM-модель CatalogChannel
**`app/db/models.py:193`** — `class CatalogChannel(Base)`. Поля: id, chat_username, title, participants, is_verified, auto_matched_country_id, auto_matched_city_id, discovered_at. Сюда добавлять `is_ignored`.

## 2. Как миграции применяются

### Автоматически
**НЕ применяются.** `app/main.py:29` вызывает `Base.metadata.create_all` (для bot-контейнера) — это создаёт таблицы при первом старте, но НЕ накатывает новые миграции.

### Монтирование
`docker-compose.yml:46-49` монтирует `migrations/` и `alembic.ini` в контейнер worker (read-write volumes):
```yaml
- ./migrations:/app/migrations
- ./alembic.ini:/app/alembic.ini
```

### Ручное применение
Миграции накатываются вручную через worker-контейнер:
```bash
docker compose exec worker alembic upgrade head
```
Или при пересборке/рестарте. Автоматизации нет.

## 3. Состояние схемы сейчас

### catalog_channels — подтверждение
```
8 колонок: id, chat_username, title, participants, is_verified,
           auto_matched_country_id, auto_matched_city_id, discovered_at
is_ignored ОТСУТСТВУЕТ ✓
```
Строк: 2522.

### alembic_version
```
Текущая БД: b11187f388a9 (add llm_decisions)
Последний файл: c2a1d3b4e5f6 (add content_hash)
Расхождение: content_hash УЖЕ есть в sent_log (миграция c2a1d3b4e5f6 фактически применена,
но не записана в alembic_version — таблица содержит 4afd135dc3f1 + b11187f388a9).
```

## 4. Риски для ALTER COLUMN is_ignored

### Объём таблицы
2522 строки. `ADD COLUMN is_ignored BOOLEAN NOT NULL DEFAULT false` — мгновенно в PostgreSQL 11+ (не требует перезаписи таблицы, только обновление каталога). Риск блокировки: **минимальный.**

### Триггеры/вьюхи
```
Триггеры: 8 шт. — все RI_ConstraintTrigger (FK CASCADE/SET NULL), системные, не затронуты ALTER.
Вьюхи: 0.
```
**Препятствий нет.** ALTER полностью безопасен.

### Downgrade
Обратимая миграция (downgrade удаляет колонку `is_ignored`). Стандартный Alembic-паттерн.

## 5. План миграции is_ignored (заготовка)

### Шаг 1: ORM-модель
Добавить в `app/db/models.py:193` (class CatalogChannel):
```python
is_ignored: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
```
Или `server_default=sa.text("false")`.

### Шаг 2: Создать ревизию
```bash
docker compose run --rm worker alembic revision --autogenerate -m "add is_ignored to catalog_channels"
```
Или вручную:
```python
def upgrade():
    op.add_column("catalog_channels", sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")))

def downgrade():
    op.drop_column("catalog_channels", "is_ignored")
```

### Шаг 3: Применить
```bash
docker compose exec worker alembic upgrade head
```

### Шаг 4: Проверить
```sql
\d catalog_channels  -- должен показать is_ignored
SELECT COUNT(*) FROM catalog_channels WHERE is_ignored = true;  -- должно быть 0
```

## ВАЖНО
⚠️ Перед миграцией — `pg_dump` (правило из CLAUDE.md §0).
⚠️ Миграция обратима (`downgrade()` удаляет колонку).
⚠️ Не запускать `docker compose run/exec/restart/up -d` при работающем worker (правило §0).
