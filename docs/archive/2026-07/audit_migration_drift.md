# Аудит дрейфа миграции is_ignored — 2026-07-04

## 0. Git
```
ahead=1, behind=0
modified: app/db/models.py (is_ignored + import text)
```

## 1. Volume/файл

### Хост vs Контейнер
```
ХОСТ (5 файлов):      4afd, b111, c2a1, ca16, da0a
КОНТЕЙНЕР (6 файлов): 0479653cd24b, 4afd, b111, c2a1, ca16, da0a (+ __pycache__)
```

**0479653cd24b — только в контейнере.** Хостовый `migrations/versions/` не синкнулся.

### Монтирование
docker-compose.yml:
```yaml
volumes:
  - ./migrations:/app/migrations
```
Bind-mount rw. Файл создан внутри worker-контейнера командой `docker compose exec worker alembic revision --autogenerate`. Bind-mount должен синкать двусторонне, но не сработал (возможно, права/owner issue: контейнер root → хост leadhunter).

## 2. Полный масштаб дрейфа ORM↔БД

`alembic check`: "Target database is not up to date" — потому что models.py уже содержит `is_ignored`, а БД нет.

Из лога autogenerate (2026-07-04 05:25), полный список ВСЕХ обнаруженных расхождений:
```
Detected added column 'catalog_channels.is_ignored'
Detected removed unique constraint 'uq_cities_country_slug' on 'cities'
Detected removed index 'idx_sent_log_content_dedup' on 'sent_log'
```

**Дрейф: ровно 3 объекта, не больше.** Первое — ожидаемое (is_ignored). Вторые два — известные: constraint и индекс есть в БД, но не в ORM-моделях.

## 3. Валидность models.py

### Импорт
```python
from sqlalchemy import (
    ...
    func,
    text,     # ← добавлен, в шапке, не в теле класса ✓
)
```
`python -c "import app.db.models"` → **OK** (без ошибок).

### Стиль поля
```python
is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
is_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False,
    server_default=text("false"), default=False)
```
Стиль совпадает: `Mapped[bool]` + `mapped_column(Boolean, ...)` ✓

## 4. Спорные объекты в БД — подтверждены

```
uq_cities_country_slug:    UNIQUE (country_id, slug) на cities  — ЕСТЬ
idx_sent_log_content_dedup: btree (user_id, content_hash, sent_at) на sent_log — ЕСТЬ
```

Оба ДОЛЖНЫ остаться. Autogenerate дропает их потому, что ORM-модели `City` и `SentLog` не декларируют соответствующие constraint/index.

## ВЫВОД

### Что нужно для чистой миграции (план, не применять)

**Вариант А (рекомендуется):** дополнить ORM-модели недостающими constraint/index, перегенерить миграцию.

В `class City` добавить `__table_args__`:
```python
__table_args__ = (
    UniqueConstraint("country_id", "slug", name="uq_cities_country_slug"),
)
```

В `class SentLog` добавить `__table_args__`:
```python
__table_args__ = (
    Index("idx_sent_log_content_dedup", "user_id", "content_hash", "sent_at"),
)
```

После этого `alembic revision --autogenerate` сгенерит только `add_column is_ignored` без лишних drop.

**Вариант Б:** вырезать лишние drop_constraint/drop_index из сгенерированного файла вручную. Быстрее, но дрейф моделей останется — следующие autogenerate снова попытаются снести constraint/index.

**Вариант В:** не использовать autogenerate, написать миграцию вручную (только add_column + серверный дефолт).
